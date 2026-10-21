"""Audit a selective native trajectory independently of its completion flag."""

from collections import Counter
import math


TOOLS = ("inspect_experiment", "simulate_candidate", "search_candidates",
         "validate_unseen_wavelengths", "export_experiment_report")
LIMITS = dict(zip(TOOLS, (3, 12, 1, 1, 2)))


def audit_trajectory(trace, run_id):
    if trace.get("run_id") != run_id or not trace.get("session_id"):
        return False, "Experiment or session identity is missing"
    if trace.get("stop_reason") != "end_turn":
        return False, "The model turn did not finish normally"
    calls, completed, counts, models = {}, [], Counter(), []
    last_seq = 0
    for event in trace.get("events", []):
        seq = event.get("seq")
        if isinstance(seq, bool) or not isinstance(seq, int) or seq <= last_seq:
            return False, "Native event sequence is not strictly increasing"
        last_seq = seq
        kind = event.get("type")
        if kind == "request/header":
            model = event.get("model")
            if not isinstance(model, str) or not model.lower().startswith("agnes"):
                return False, "A model request is not identified as Agnes"
            models.append(model)
        elif kind == "tool/call":
            name, args, identity = event.get("tool"), event.get("args"), event.get("tool_use_id")
            discovery = (name == "unapproved_tool" and event.get("native_name") == "mcp_manage"
                         and isinstance(args, dict) and args.get("action") in ("list", "status"))
            if discovery:
                if not identity or identity in calls:
                    return False, "Discovery call identity is duplicated"
                calls[identity] = [name, False]
                continue
            if name not in TOOLS or not isinstance(args, dict) or args.get("run_id") != run_id:
                return False, "A tool call is outside this numerical experiment"
            if not identity or identity in calls:
                return False, "Tool call identity is missing or duplicated"
            permitted = {"run_id"}
            if name == "simulate_candidate":
                permitted |= {"diameter_nm", "n_real", "k"}
                for key, low, high in (("diameter_nm", 50, 500), ("n_real", 1.05, 2.8), ("k", 0, .35)):
                    value = args.get(key)
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                        return False, "A candidate is outside the physical bounds"
            elif name == "search_candidates":
                permitted |= {"generations", "seed"}
                generation = args.get("generations", 20)
                seed = args.get("seed", 7)
                if isinstance(generation, bool) or not isinstance(generation, int) or not 1 <= generation <= 15 or isinstance(seed, bool) or not isinstance(seed, int) or seed != 7:
                    return False, "Search exceeds the declared budget"
                if "inspect_experiment" not in completed or completed.count("simulate_candidate") < 2:
                    return False, "Search preceded the required initial feedback trials"
            elif name == "validate_unseen_wavelengths":
                if "search_candidates" not in completed or completed.count("simulate_candidate") < 3 or "simulate_candidate" not in completed[completed.index("search_candidates") + 1:]:
                    return False, "Validation preceded a post-search feedback trial"
            elif name == "export_experiment_report" and "validate_unseen_wavelengths" not in completed:
                return False, "Reporting preceded validation"
            if name in ("simulate_candidate", "search_candidates") and "validate_unseen_wavelengths" in completed:
                return False, "Fitting continued after holdout disclosure"
            if set(args) - permitted:
                return False, "Unexpected tool arguments"
            counts[name] += 1
            if counts[name] > LIMITS[name]:
                return False, "Tool call budget exceeded"
            calls[identity] = [name, False]
        elif kind == "tool/result":
            identity = event.get("tool_use_id")
            call = calls.get(identity)
            if not call or call[1] or event.get("tool") != call[0]:
                return False, "A tool result has no unique matching call"
            call[1] = True
            if event.get("is_error") is False and call[0] in TOOLS:
                completed.append(call[0])
    if not models or set(models) != set(trace.get("models", [])):
        return False, "Native model headers do not match the model summary"
    if any(not result[1] for result in calls.values()) or not all(name in completed for name in TOOLS):
        return False, "Required tool results are incomplete"
    return True, "Ordered Agnes and numerical-tool trajectory verified"

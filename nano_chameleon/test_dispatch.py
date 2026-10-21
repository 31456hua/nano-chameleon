"""Verify the dispatcher only approves the bounded experiment workflow."""

import unittest

from agh_dispatch import ApprovalPolicy, redact, tool_payload
from agh_evidence import audit_trajectory


RUN = "a" * 32
PREFIX = "mcp_nano_chameleon_4608cd0d_"


class DispatchPolicyTests(unittest.TestCase):
    def test_rejects_unknown_tools_foreign_ids_and_extra_arguments(self):
        policy = ApprovalPolicy(RUN)
        for tool, args in (("shell", {"run_id": RUN}),
                           (PREFIX + "inspect_experiment", {"run_id": "b" * 32}),
                           (PREFIX + "inspect_experiment", {"run_id": RUN, "path": "secret"})):
            self.assertFalse(policy.decide(tool, args)[0])

    def test_candidate_bounds_and_nonfinite_values(self):
        policy = ApprovalPolicy(RUN)
        base = {"run_id": RUN, "diameter_nm": 250, "n_real": 2, "k": .01}
        for key, value in (("diameter_nm", 501), ("n_real", float("nan")), ("k", -.1), ("k", True)):
            self.assertFalse(policy.decide(PREFIX + "simulate_candidate", {**base, key: value})[0])
        self.assertTrue(policy.decide(PREFIX + "simulate_candidate", base)[0])

    def test_search_budget_matches_predeclared_baseline(self):
        policy = ApprovalPolicy(RUN)
        policy.completed = ["inspect_experiment", "simulate_candidate", "simulate_candidate"]
        base = {"run_id": RUN, "generations": 15, "seed": 7}
        for key, value in (("generations", 16), ("generations", True), ("seed", 19)):
            self.assertFalse(policy.decide(PREFIX + "search_candidates", {**base, key: value})[0])
        self.assertTrue(policy.decide(PREFIX + "search_candidates", base)[0])
        self.assertFalse(policy.decide(PREFIX + "search_candidates", base)[0])

    def test_final_validation_requires_feedback_trial_after_search(self):
        policy = ApprovalPolicy(RUN)
        args = {"run_id": RUN}
        self.assertFalse(policy.decide(PREFIX + "validate_unseen_wavelengths", args)[0])
        policy.completed = ["simulate_candidate"] * 3 + ["search_candidates"]
        self.assertFalse(policy.decide(PREFIX + "validate_unseen_wavelengths", args)[0])
        policy.completed.append("simulate_candidate")
        self.assertTrue(policy.decide(PREFIX + "validate_unseen_wavelengths", args)[0])
        self.assertFalse(policy.decide(PREFIX + "validate_unseen_wavelengths", args)[0])

    def test_report_requires_successful_validation(self):
        policy = ApprovalPolicy(RUN)
        self.assertFalse(policy.decide(PREFIX + "export_experiment_report", {"run_id": RUN})[0])
        policy.completed.append("validate_unseen_wavelengths")
        self.assertTrue(policy.decide(PREFIX + "export_experiment_report", {"run_id": RUN})[0])

    def test_result_parser_and_redaction(self):
        self.assertEqual(tool_payload({"content": [{"type": "text", "text": '{"trial": 7}'}]}), {"trial": 7})
        self.assertEqual(tool_payload({"structured": {"result": {"trial": 8}}}), {"trial": 8})
        self.assertNotIn("testcredential", redact("Bearer testcredential"))

    def test_search_requires_initial_feedback_and_fit_stops_after_validation(self):
        policy = ApprovalPolicy(RUN)
        self.assertFalse(policy.decide(PREFIX + "search_candidates", {"run_id": RUN, "generations": 15})[0])
        policy.completed = ["validate_unseen_wavelengths"]
        self.assertFalse(policy.decide(PREFIX + "simulate_candidate", {"run_id": RUN, "diameter_nm": 250, "n_real": 2, "k": .01})[0])


def example_trace():
    events = [{"seq": 1, "type": "request/header", "model": "agnes-3.0-flash"}]
    order = ["inspect_experiment", "simulate_candidate", "simulate_candidate", "search_candidates",
             "simulate_candidate", "validate_unseen_wavelengths", "export_experiment_report"]
    for i, name in enumerate(order):
        args = {"run_id": RUN}
        if name == "simulate_candidate":
            args.update(diameter_nm=200 + i, n_real=2, k=.01)
        elif name == "search_candidates":
            args.update(generations=15, seed=7)
        events.append({"seq": 2*i + 2, "type": "tool/call", "tool": name, "args": args, "tool_use_id": str(i)})
        events.append({"seq": 2*i + 3, "type": "tool/result", "tool": name, "is_error": False, "tool_use_id": str(i)})
    return {"run_id": RUN, "session_id": "test-session", "stop_reason": "end_turn", "models": ["agnes-3.0-flash"], "events": events}


class EvidenceAuditTests(unittest.TestCase):
    def test_complete_ordered_trace_passes(self):
        self.assertTrue(audit_trajectory(example_trace(), RUN)[0])

    def test_failure_flags_non_agnes_requests_and_foreign_ids_fail(self):
        for change in (lambda t: t.update(stop_reason="error"),
                       lambda t: t["events"][0].update(model="other-model"),
                       lambda t: t["events"][1]["args"].update(run_id="b"*32),
                       lambda t: t["events"][8].update(is_error=True)):
            trace = example_trace()
            change(trace)
            self.assertFalse(audit_trajectory(trace, RUN)[0])

    def test_reordered_or_duplicate_events_and_missing_export_fail(self):
        for change in (lambda t: t["events"][2].update(seq=1),
                       lambda t: t["events"].pop(),
                       lambda t: t["events"][5].update(tool_use_id="0"),
                       lambda t: t["events"][7]["args"].update(generations=16)):
            trace = example_trace()
            change(trace)
            self.assertFalse(audit_trajectory(trace, RUN)[0])

    def test_discovery_only_allows_native_read_only_catalog_actions(self):
        for action, allowed in (("list", True), ("status", True), ("commit", False), ("prepare", False)):
            trace = example_trace()
            for event in trace["events"][1:]:
                event["seq"] += 2
            trace["events"][1:1] = [
                {"seq": 2, "type": "tool/call", "tool": "unapproved_tool", "native_name": "mcp_manage",
                 "tool_use_id": "catalog", "args": {"action": action}},
                {"seq": 3, "type": "tool/result", "tool": "unapproved_tool", "tool_use_id": "catalog", "is_error": False},
            ]
            self.assertEqual(audit_trajectory(trace, RUN)[0], allowed)


if __name__ == "__main__":
    unittest.main()

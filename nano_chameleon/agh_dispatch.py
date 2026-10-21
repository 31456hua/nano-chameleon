"""Bounded experiment queue using the official SDK and existing local AGH daemon."""

from __future__ import annotations

import argparse
from copy import deepcopy
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
from urllib.parse import quote

from engine import public_status
from agh_evidence import audit_trajectory


ROOT = Path(__file__).resolve().parent
TOOLS = ("inspect_experiment", "simulate_candidate", "search_candidates",
         "validate_unseen_wavelengths", "export_experiment_report")
TOOL_NAME = re.compile(r"^mcp_nano_chameleon_[0-9a-f]{8}_(" + "|".join(TOOLS) + r")$")
LIMITS = dict(zip(TOOLS, (3, 12, 1, 1, 2)))


def now():
    return datetime.now(timezone.utc).isoformat()


def redact(text):
    text = re.sub(r"sk-[A-Za-z0-9_-]{16,}", "[REDACTED]", str(text))
    return re.sub(r"(?i)Bearer\s+\S+", "Bearer [REDACTED]", text)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


class ApprovalPolicy:
    """Approve only this job's reviewed numerical tools, once per request."""

    def __init__(self, run_id):
        self.run_id = run_id
        self.approvals = Counter()
        self.completed = []

    def decide(self, tool, args):
        match = TOOL_NAME.fullmatch(tool or "")
        if not match or not isinstance(args, dict) or args.get("run_id") != self.run_id:
            return False, "Tool or experiment outside this job"
        name = match.group(1)
        permitted = {"run_id"}
        if name == "simulate_candidate":
            permitted |= {"diameter_nm", "n_real", "k"}
            for key, bounds in (("diameter_nm", (50, 500)), ("n_real", (1.05, 2.8)), ("k", (0, .35))):
                value = args.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not bounds[0] <= value <= bounds[1]:
                    return False, "Candidate outside reviewed physical bounds"
        elif name == "search_candidates":
            permitted |= {"generations", "seed"}
            for key, default, bounds in (("generations", 20, (1, 15)), ("seed", 7, (7, 7))):
                value = args.get(key, default)
                if isinstance(value, bool) or not isinstance(value, int) or not bounds[0] <= value <= bounds[1]:
                    return False, "Search exceeds job bounds"
        if set(args) - permitted:
            return False, "Unexpected tool arguments"
        if name in ("simulate_candidate", "search_candidates") and "validate_unseen_wavelengths" in self.completed:
            return False, "Experiment is already sealed"
        if name == "search_candidates" and ("inspect_experiment" not in self.completed or self.completed.count("simulate_candidate") < 2):
            return False, "Inspect and two initial feedback trials must precede search"
        if self.approvals[name] >= LIMITS[name]:
            return False, "Tool budget exhausted"
        if name == "validate_unseen_wavelengths":
            if self.completed.count("simulate_candidate") < 3 or "search_candidates" not in self.completed:
                return False, "Required feedback trials have not completed"
            if self.completed.index("search_candidates") > len(self.completed) - 1 - self.completed[::-1].index("simulate_candidate"):
                return False, "A feedback trial must follow the search"
        if name == "export_experiment_report" and "validate_unseen_wavelengths" not in self.completed:
            return False, "Validation must precede reporting"
        self.approvals[name] += 1
        return True, "Within this experiment's approved test scope"


def tool_payload(data):
    if isinstance(data.get("structured"), dict):
        result = data["structured"]
        return result.get("result", result)
    for block in data.get("content", []):
        if block.get("type") == "text":
            try:
                result = json.loads(block.get("text", ""))
                if isinstance(result, dict):
                    return result
            except (ValueError, TypeError):
                pass
    return {}


class AcpRunner:
    def __init__(self, sdk_root, profile, workspace, evidence_path, run_id):
        self.policy = ApprovalPolicy(run_id)
        self.path = evidence_path
        self.trace = {"protocol": "AGH official SDK; existing verified local daemon", "started_at": now(),
                      "run_id": run_id, "profile": profile, "complete": False,
                      "events": [], "approvals": [], "models": [], "session_id": None}
        self.inbox = queue.Queue()
        self.calls = {}
        self.next_id = 0
        self.last_seq = 0
        source_repo = sdk_root.resolve()
        tsx = source_repo / "node_modules" / "tsx" / "dist" / "cli.mjs"
        self.process = subprocess.Popen(
            ["node", str(tsx), str(ROOT / "agh_shared_bridge.mts"), profile, str(workspace), str(source_repo)],
            cwd=str(workspace), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1,
        )
        threading.Thread(target=self._read, args=(self.process.stdout,), daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _read(self, stream):
        for line in stream:
            try:
                self.inbox.put(json.loads(line))
            except ValueError:
                self.inbox.put({"transport_error": "Invalid ACP JSON frame"})
        self.inbox.put({"transport_error": "ACP process closed"})

    def _drain_stderr(self):
        for line in self.process.stderr:
            self.trace["last_runtime_note"] = redact(line.strip())[:300]
            notes = self.trace.setdefault("runtime_notes", [])
            notes.append(self.trace["last_runtime_note"])
            del notes[:-20]

    def send(self, message):
        self.process.stdin.write(json.dumps(message, ensure_ascii=False, allow_nan=False) + "\n")
        self.process.stdin.flush()

    def persist(self):
        write_json(self.path, self.trace)

    def handle(self, message):
        method = message.get("method")
        params = message.get("params", {})
        if method == "session/request_permission":
            call = params.get("toolCall", {})
            name = call.get("_meta", {}).get("ai.agnes.harness", {}).get("tool")
            allowed, reason = self.policy.decide(name, call.get("rawInput"))
            options = params.get("options", [])
            kind = "allow_once" if allowed else "reject_once"
            option = next((o for o in options if o.get("kind") == kind), None)
            outcome = {"outcome": "selected", "optionId": option["optionId"]} if option else {"outcome": "cancelled"}
            self.send({"jsonrpc": "2.0", "id": message["id"], "result": {"outcome": outcome}})
            self.trace["approvals"].append({"tool": name, "allowed_once": allowed and option is not None, "reason": reason, "at": now()})
            self.persist()
        elif method == "_agnes/v1/session.event":
            self.event(params.get("event", {}))
        elif method and "id" in message:
            self.send({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": "Client operation outside numerical evaluation scope"}})

    def event(self, event):
        seq = event.get("seq", 0)
        if seq <= self.last_seq:
            return
        self.last_seq = seq
        kind = event.get("type")
        data = event.get("data", {})
        row = {"seq": seq, "type": kind, "ts": event.get("ts")}
        if kind == "request/header":
            model = redact(data.get("model", ""))
            if model not in self.trace["models"]:
                self.trace["models"].append(model)
            row["model"] = model
        elif kind == "tool/call":
            match = TOOL_NAME.fullmatch(data.get("name", ""))
            name = match.group(1) if match else "unapproved_tool"
            self.calls[data.get("toolUseId")] = name
            row.update(tool=name, native_name=redact(data.get("name", "")), tool_use_id=data.get("toolUseId"))
            if match:
                row["args"] = data.get("args")
        elif kind == "tool/result":
            name = self.calls.get(data.get("toolUseId"), "unknown_tool")
            error = data.get("isError", True)
            row.update(tool=name, tool_use_id=data.get("toolUseId"), is_error=error, code=data.get("code"))
            if not error and name in TOOLS:
                self.policy.completed.append(name)
                payload = tool_payload(data)
                row["result"] = {key: value for key, value in payload.items() if key in {
                    "trial", "trial_count", "holdout_count", "sealed", "diameter_nm", "n_real", "k",
                    "train_rmse", "holdout_rmse", "parameters", "best_trial", "report_path"}}
            print(f"AGH tool: {name}; {'failed' if error else 'completed'}", flush=True)
        elif kind == "assistant/message":
            row["text"] = redact("".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"))
        elif kind == "turn/end":
            row["reason"] = data.get("reason")
        else:
            return
        self.trace["events"].append(row)
        self.persist()

    def rpc(self, method, params, timeout=30):
        self.next_id += 1
        rpc_id = self.next_id
        self.send({"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"AGH timeout during {method}")
            try:
                message = self.inbox.get(timeout=min(remaining, 1))
            except queue.Empty:
                continue
            if "transport_error" in message:
                raise RuntimeError(message["transport_error"] + "; " + self.trace.get("last_runtime_note", "No startup diagnostic"))
            if message.get("id") == rpc_id and not message.get("method"):
                if "error" in message:
                    error = message["error"]
                    raise RuntimeError(f"AGH {method}: {error.get('code')} {redact(error.get('message', ''))[:200]}")
                return message.get("result", {})
            self.handle(message)

    def close(self):
        if self.process.poll() is None:
            try:
                if self.trace["session_id"] and not self.trace["complete"]:
                    self.send({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": self.trace["session_id"]}})
                self.process.stdin.close()
                self.process.wait(timeout=15)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                self.process.terminate()
                self.process.wait(timeout=10)


def prompt_for(case):
    if case.get("task"):
        return case["task"]
    run_id = case.get("run_id", case.get("agh_run_id"))
    return (
        f"执行纳米变色龙评测，实验 ID {run_id}。只能调用 nano-chameleon 的五个工具。"
        "先 inspect_experiment，根据训练光谱规划；执行至少两次不同的 simulate_candidate，并用误差反馈调整。"
        "再 search_candidates(generations=15,seed=7)，根据返回的最优参数设计至少一次新的 simulate_candidate。"
        "总预算：simulate_candidate 最多12次，search_candidates 最多1次，每次最多15代。"
        "只用训练数据，不读取文件、不调用 shell/web/其他工具，不查看原始CSV或留出目标。"
        "最后仅一次 validate_unseen_wavelengths 锁定参数，然后 export_experiment_report。"
        "报告训练/留出RMSE和参数，指出逆问题非唯一性、噪声和模型误差可能影响解释。"
        "如果误差仍明显偏高，诚实记录失败或模型不匹配，不能在揭盲后继续拟合。"
        "这是一条待评测目标，没有已知答案提供给你。发生工具异常时根据返回信息处理，勿虚构结果。"
    )


def run_case(sdk_root, profile, workspace, case, evidence, timeout, previous=None):
    run_id = case.get("run_id", case.get("agh_run_id"))
    workspace.mkdir(parents=True, exist_ok=True)
    runner = AcpRunner(sdk_root, profile, workspace, evidence, run_id)
    if previous:
        runner.trace = deepcopy(previous)
        runner.trace.setdefault("recoveries", []).append({"started_at": now(), "previous_failure": previous.get("failure"),
                                                         "scope": "Sealed experiment; no further fitting or validation"})
        runner.trace.pop("failure", None)
        runner.trace["complete"] = False
        runner.last_seq = max((e["seq"] for e in runner.trace["events"]), default=0)
        for event in runner.trace["events"]:
            name = event.get("tool")
            if event["type"] == "tool/call":
                runner.calls[event.get("tool_use_id")] = name
                if name in TOOLS:
                    runner.policy.approvals[name] += 1
            elif event["type"] == "tool/result" and event.get("is_error") is False and name in TOOLS:
                runner.policy.completed.append(name)
    runner.trace["scenario_id"] = case["scenario_id"]
    try:
        runner.rpc("initialize", {"protocolVersion": 1, "clientCapabilities": {
            "fs": {"readTextFile": False, "writeTextFile": False},
            "_meta": {"ai.agnes.harness": {"capabilities": {"permission": True}}}}})
        session = runner.rpc("session/load" if previous else "session/new", {"cwd": str(workspace), "mcpServers": [],
                            **({"sessionId": previous["session_id"]} if previous else {})})
        runner.trace["session_id"] = session["sessionId"]
        runner.trace["session_url"] = "http://127.0.0.1:4177/?session=" + quote(session["sessionId"], safe="")
        runner.persist()
        runner.rpc("_agnes/v1/session.attach", {"sessionId": session["sessionId"], "filter": {"acpUpdates": False}})
        if previous:
            for event in runner.trace["events"]:
                if event.get("native_name") == "mcp_manage" and "args" not in event:
                    detail = runner.rpc("session/read_tool_detail", {"sessionId": session["sessionId"], "callSeq": event["seq"]})
                    if detail.get("name") == "mcp_manage":
                        event["args"] = detail["args"]
                        event["metadata_verified_from_native_detail"] = True
        prompt = (f"恢复实验 {run_id} 的回合收尾。该实验已完成未见波长验证并锁定，前一回合在导出报告后报错。"
                  "不要 simulate_candidate、search_candidates 或再次 validate_unseen_wavelengths；不得在揭盲后重新拟合。"
                  "只用 inspect_experiment 确认现有结果，再 export_experiment_report。最后用中文简短报告参数、训练与留出 RMSE、"
                  "模型局限和此次收尾恢复；不要读文件、修改 MCP 设置或调用其他工具。" if previous else prompt_for(case))
        result = runner.rpc("session/prompt", {"sessionId": session["sessionId"],
            "prompt": [{"type": "text", "text": prompt}]}, timeout=timeout)
        runner.trace["stop_reason"] = result.get("stopReason")
        # Drain queued terminal events; the reply and subscription have independent delivery.
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            try:
                runner.handle(runner.inbox.get(timeout=.1))
            except queue.Empty:
                continue
        status = public_status(ROOT / "runs", run_id)
        verified, reason = audit_trajectory(runner.trace, run_id)
        complete = verified and status["sealed"]
        runner.trace["audit"] = {"verified": verified, "reason": reason}
        runner.trace["complete"] = bool(complete)
        runner.trace["trial_count"] = status["trial_count"]
        if status["sealed"]:
            runner.trace["validation"] = {key: status["final"][key] for key in ("parameters", "train_rmse", "holdout_rmse")}
        if not complete:
            runner.trace["failure"] = "Required native model/tool evidence or final experiment state is incomplete"
    except Exception as error:
        runner.trace["failure"] = redact(error)
    finally:
        status = public_status(ROOT / "runs", run_id)
        runner.trace["trial_count"] = status["trial_count"]
        if status["sealed"]:
            runner.trace["validation"] = {key: status["final"][key] for key in ("parameters", "train_rmse", "holdout_rmse")}
        runner.trace["finished_at"] = now()
        runner.persist()
        runner.close()
    return runner.trace


def main():
    parser = argparse.ArgumentParser(description="Run a bounded, sequential AGH benchmark queue")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--sdk-root", type=Path, default=ROOT.parent.parent / "work" / "agh-src" / "agnes-harness-main")
    parser.add_argument("--profile", default="local-dev")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--retry-incomplete", action="store_true", help="Preserve and retry an incomplete unsealed job")
    parser.add_argument("--finish-sealed-incomplete", action="store_true", help="Resume only reporting in a sealed job's original session")
    parser.add_argument("--workspace-root", type=Path, default=ROOT.parent.parent / "work" / "agh_batch")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    cases = manifest if isinstance(manifest, list) else manifest.get("tasks", manifest.get("cases", []))
    if not cases or not 1 <= args.limit <= 4 or not 30 <= args.timeout <= 900:
        parser.error("Need 1-4 tasks and a 30-900 second timeout")
    summary = []
    for required in (args.sdk_root / "node_modules/tsx/dist/cli.mjs",
                     args.sdk_root / "packages/system-node/dist/native/agnes-system.node"):
        if not required.is_file():
            parser.error(f"Official SDK runtime component missing: {required}")
    for case in cases[:args.limit]:
        run_id = case.get("run_id", case.get("agh_run_id"))
        evidence = args.manifest.parent / f"{case['scenario_id']}.agh.json"
        previous = json.loads(evidence.read_text(encoding="utf-8")) if evidence.exists() else None
        if (previous and args.finish_sealed_incomplete and not previous.get("complete")
                and previous.get("session_id") and public_status(ROOT / "runs", run_id)["sealed"]):
            archive = evidence.with_name(evidence.stem + ".before-recovery-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
            write_json(archive, previous)
            print(f"Recovering sealed AGH job without fitting: {case['scenario_id']}", flush=True)
            trace = run_case(args.sdk_root, args.profile, args.workspace_root / args.manifest.parent.name / case["scenario_id"], case, evidence, args.timeout, previous)
            print(f"Recovery: complete={trace.get('complete')}; {trace.get('failure', '')}", flush=True)
            summary.append({"run_id": run_id, "scenario_id": case["scenario_id"], "model": ", ".join(trace.get("models", [])),
                            "session_id": trace.get("session_id"), "evidence_path": str(evidence.resolve()), "complete": trace.get("complete", False)})
            write_json(args.manifest.parent / "agh_evidence_summary.json", summary)
            continue
        if evidence.exists() and args.retry_incomplete:
            previous = json.loads(evidence.read_text(encoding="utf-8"))
            if not previous.get("complete") and not public_status(ROOT / "runs", run_id)["sealed"]:
                evidence.replace(evidence.with_name(evidence.stem + ".attempt-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json"))
        if evidence.exists():
            trace = json.loads(evidence.read_text(encoding="utf-8"))
            print(f"Existing job retained: {case['scenario_id']}; complete={trace.get('complete')}", flush=True)
        elif public_status(ROOT / "runs", run_id)["sealed"]:
            trace = {"run_id": run_id, "scenario_id": case["scenario_id"], "complete": False,
                     "failure": "Already sealed without this dispatcher evidence; retained without rerun"}
        else:
            print(f"Starting AGH job: {case['scenario_id']}", flush=True)
            trace = run_case(args.sdk_root, args.profile, args.workspace_root / args.manifest.parent.name / case["scenario_id"], case, evidence, args.timeout)
            print(f"Finished AGH job: {case['scenario_id']}; complete={trace.get('complete')}; {trace.get('failure', '')}", flush=True)
        summary.append({"run_id": run_id, "scenario_id": case["scenario_id"], "model": ", ".join(trace.get("models", [])),
                        "session_id": trace.get("session_id"), "evidence_path": str(evidence.resolve()), "complete": trace.get("complete", False)})
        write_json(args.manifest.parent / "agh_evidence_summary.json", summary)
    print(json.dumps({"jobs": len(summary), "completed": sum(item["complete"] for item in summary),
                      "evidence": str(args.manifest.parent / "agh_evidence_summary.json")}, ensure_ascii=False), flush=True)
    return 0 if all(item["complete"] for item in summary) else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Loopback-only competition workbench; manual trials never masquerade as AGH."""

import argparse
import csv
import io
import json
import math
from pathlib import Path
import secrets

import numpy as np
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route
import uvicorn

from agh_evidence import audit_trajectory
from benchmark import generate_scenarios, normalization_scale
from colour_preview import transmission_colour
from engine import create_experiment, finalize, optimize, public_status, report_record, run_trial, spectrum, validate_rows
from report import write_report


ROOT = Path(__file__).resolve().parent
SUITE = ROOT / "benchmarks/20261010T151242Z_161152a2"
CASES = {"clean_a": ("合成目标 A", "69f40ac21827433a98ad5a231b92706c"),
         "clean_b": ("合成目标 B", "6316c87602d84c2fab5e20a6ed5bcad9"),
         "noisy": ("带噪声目标", "4ca3625df4674a17a83544d289127441"),
         "mismatch": ("色散失配目标", "93dd00121a0c415681d5d3c0d66770fa")}


def candidates(trials):
    chosen = []
    for trial in sorted(trials, key=lambda t: t["train_rmse"]):
        point = np.asarray([trial["diameter_nm"] / 450, trial["n_real"] / 1.75, trial["k"] / .35])
        if all(np.linalg.norm(point - p) >= .025 for _, p in chosen):
            chosen.append((trial, point))
        if len(chosen) == 3:
            break
    return [t for t, _ in chosen]


def snapshot(store, run_id):
    status = public_status(store, run_id)
    # This is the manual store only; never expose an unsealed shared MCP record.
    record = json.loads((Path(store) / f"{run_id}.json").read_text(encoding="utf-8"))
    status.update(trials=record["trials"], candidates=candidates(record["trials"]), source="manual")
    return status


class LocalGuard(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        allowed = request.app.state.hosts
        host = request.headers.get("host", "")
        if host not in allowed:
            return JSONResponse({"error": "Only the configured loopback host is accepted"}, status_code=403)
        if request.method == "POST":
            if request.headers.get("origin") != "http://" + host or not secrets.compare_digest(
                    request.headers.get("x-demo-token", ""), request.app.state.token):
                return JSONResponse({"error": "Local request authorization failed"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; worker-src blob:; frame-ancestors 'none'")
        return response


async def config(request):
    return JSONResponse({"token": request.app.state.token, "cases": [{"id": k, "label": v[0]} for k, v in CASES.items()]})


async def asset(request):
    name = request.path_params["name"]
    if name not in {"index.html", "app.js", "style.css", "plotly.min.js", "lucide.min.js", "angular-scattering.png"}:
        return JSONResponse({"error": "Unknown asset"}, status_code=404)
    return FileResponse(ROOT / "demo_web" / name)


async def home(request):
    return FileResponse(ROOT / "demo_web/index.html")


async def evidence(request):
    case = request.path_params["case"]
    if case not in CASES:
        return JSONResponse({"error": "Unknown case"}, status_code=404)
    run_id = CASES[case][1]
    status = public_status(ROOT / "runs", run_id)
    if not status["sealed"]:
        return JSONResponse({"error": "Evidence is not sealed"}, status_code=409)
    record = report_record(ROOT / "runs", run_id)
    trace = json.loads((SUITE / f"{case}.agh.json").read_text(encoding="utf-8"))
    verified, reason = audit_trajectory(trace, run_id)
    manifest = json.loads((SUITE / "agh_tasks_public.json").read_text(encoding="utf-8"))
    criterion = next(c["criteria"]["holdout_nrmse_limit"] for c in manifest["cases"] if c["case_id"] == case)
    nrmse = status["final"]["holdout_rmse"] / normalization_scale([p["qsca"] for p in status["training"]])
    status.update(source="agh", trials=record["trials"], candidates=candidates(record["trials"]),
                  evidence={"verified": verified, "reason": reason, "models": trace["models"], "session_url": trace["session_url"],
                            "events": trace["events"], "recoveries": trace.get("recoveries", []),
                            "holdout_nrmse": nrmse, "limit_nrmse": criterion, "criterion_met": nrmse <= criterion})
    return JSONResponse(status)


def numeric(data, name, default=None):
    value = data.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"Invalid numeric field: {name}")
    return float(value)


async def action(request):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 120000:
            return JSONResponse({"error": "Target upload too large"}, status_code=413)
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("A JSON object is required")
        operation = request.path_params["operation"]
        store = request.app.state.store
        if operation == "colour":
            parameters = [numeric(data, name) for name in ("diameter_nm", "n_real", "k")]
            return JSONResponse(transmission_colour(*parameters, numeric(data, "n_env", 1), numeric(data, "optical_depth", .25)))
        if operation == "create":
            if "csv" in data:
                if not isinstance(data["csv"], str):
                    raise ValueError("CSV must be text")
                reader = csv.DictReader(io.StringIO(data["csv"].lstrip("\ufeff")))
                if not reader.fieldnames or not {"wavelength_nm", "qsca"}.issubset(reader.fieldnames):
                    raise ValueError("CSV needs wavelength_nm and qsca columns")
                rows = validate_rows((float(r["wavelength_nm"]), float(r["qsca"])) for r in reader)
            else:
                preset = next((s for s in generate_scenarios() if s["case_id"] == data.get("case")), None)
                if preset is None or data["case"] not in CASES:
                    raise ValueError("Unknown target")
                rows = list(zip(preset["wavelengths_nm"], preset["observed_qsca"]))
            run_id = create_experiment(store, rows, numeric(data, "n_env", 1.0))
            return JSONResponse(snapshot(store, run_id))
        run_id = data.get("run_id")
        status = public_status(store, run_id)
        if request.app.state.searching and operation in ("trial", "validate", "report"):
            return JSONResponse({"error": "Wait for the active numerical search to finish"}, status_code=409)
        if operation in ("preview", "trial"):
            if status["sealed"]:
                raise ValueError("Experiment is sealed after validation; create a new run.")
            parameters = [numeric(data, name) for name in ("diameter_nm", "n_real", "k")]
            if operation == "trial":
                await run_in_threadpool(run_trial, store, run_id, *parameters)
                return JSONResponse(snapshot(store, run_id))
            curve = spectrum([p["wavelength_nm"] for p in status["training"]], *parameters, status["n_env"])
            colour = transmission_colour(*parameters, status["n_env"], numeric(data, "optical_depth", .25))
            return JSONResponse({"curve": curve.tolist(), "colour": colour})
        if operation == "search":
            if status["sealed"] or request.app.state.searching:
                return JSONResponse({"error": "Search unavailable or already running"}, status_code=409)
            request.app.state.searching = True
            try:
                await run_in_threadpool(optimize, store, run_id, 5, 7)
            finally:
                request.app.state.searching = False
            return JSONResponse(snapshot(store, run_id))
        if operation == "validate":
            await run_in_threadpool(finalize, store, run_id)
            return JSONResponse(snapshot(store, run_id))
        if operation == "report":
            await run_in_threadpool(write_report, report_record(store, run_id), ROOT / "demo_reports")
            return JSONResponse({"url": f"/report/{run_id}"})
        raise ValueError("Unknown operation")
    except (ValueError, TypeError, KeyError, StopIteration, OverflowError) as error:
        return JSONResponse({"error": str(error)}, status_code=400)


async def report_file(request):
    run_id = request.path_params["run_id"]
    try:
        report_record(request.app.state.store, run_id)
        path = ROOT / "demo_reports" / f"{run_id}.html"
        if not path.is_file():
            return JSONResponse({"error": "Export report first"}, status_code=404)
        return FileResponse(path, headers={"Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'none'"})
    except ValueError as error:
        return JSONResponse({"error": str(error)}, status_code=400)


async def evidence_report(request):
    case = request.path_params["case"]
    if case not in CASES:
        return JSONResponse({"error": "Unknown case"}, status_code=404)
    record = report_record(ROOT / "runs", CASES[case][1])
    path = await run_in_threadpool(write_report, record, ROOT / "demo_reports")
    return FileResponse(path, headers={"Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'none'"})


def create_app(store=None, port=4190):
    app = Starlette(routes=[Route("/", home), Route("/assets/{name}", asset), Route("/api/config", config),
                            Route("/api/evidence/{case}", evidence), Route("/api/{operation}", action, methods=["POST"]),
                            Route("/evidence-report/{case}", evidence_report),
                            Route("/report/{run_id}", report_file)])
    app.state.store = Path(store) if store else ROOT / "demo_runs"
    app.state.token = secrets.token_urlsafe(32)
    app.state.hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    app.state.searching = False
    app.add_middleware(LocalGuard)
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=4190)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a port from 1024 to 65535")
    uvicorn.run(create_app(port=args.port), host="127.0.0.1", port=args.port, log_level="warning")

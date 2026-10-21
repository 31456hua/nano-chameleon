"""Bounded, reproducible benchmark controller; never runs an AGH model itself.

Private generated targets stay outside the agent workspace. The public manifest
contains sealed experiment IDs and instructions, and the baseline is explicitly
a SciPy physics optimizer, not an AGH/Agnes result.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import io
import json
import platform
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import miepython
import numpy as np
import scipy

from engine import (
    BOUNDS, create_experiment, finalize, optimize, public_status, report_record,
    spectrum,
)
from agh_evidence import audit_trajectory


ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent
DEFAULT_PRIVATE = WORKSPACE / "work" / "benchmark_private"
DEFAULT_AGENT_WORKSPACE = WORKSPACE / "work" / "benchmark_agh_workspace"
DEFAULT_SEEDS = (7, 19, 43)
PARAMETERS = ("diameter_nm", "n_real", "k")
NORMALIZATION = "RMSE / RMS(observed training Qsca), with denominator floor 1e-8"


def split_indices(count):
    """Match engine.create_experiment exactly, including endpoint protection."""
    held = np.asarray(list(range(2, count - 1, 5)), dtype=int)
    train = np.asarray([i for i in range(count) if i not in set(held)], dtype=int)
    return train, held


def normalization_scale(observed):
    values = np.asarray(observed, dtype=float)
    if values.ndim != 1 or not len(values) or not np.all(np.isfinite(values)):
        raise ValueError("Normalization requires finite, nonempty training samples.")
    return max(float(np.sqrt(np.mean(values ** 2))), 1e-8)


def generate_scenarios():
    wavelengths = np.linspace(390.0, 810.0, 43)
    train, held = split_indices(len(wavelengths))
    definitions = [
        ("clean_a", "Clean target A", "clean", (183.47, 1.8732, 0.0268), 0.01),
        ("clean_b", "Clean target B", "clean", (317.83, 2.4137, 0.0731), 0.01),
        ("lower_boundary", "Near lower bounds", "boundary", (53.71, 1.0613, 0.0067), 0.01),
        ("upper_boundary", "Near upper bounds", "boundary", (494.29, 2.7631, 0.3437), 0.01),
        ("noisy", "Deterministic measurement noise", "noisy", (248.63, 2.1674, 0.0382), 0.06),
        ("mismatch", "Dispersive model mismatch", "mismatch", (237.61, None, None), 0.05),
    ]
    scenarios = []
    for case_id, label, kind, truth, threshold in definitions:
        if kind == "mismatch":
            n = 2.10 + 0.45 * ((550.0 / wavelengths) ** 2 - 1.0)
            k = 0.04 + 0.12 * np.exp(-((wavelengths - 500.0) / 55.0) ** 2)
            clean = np.asarray([
                spectrum([w], truth[0], float(nr), float(ki))[0]
                for w, nr, ki in zip(wavelengths, n, k)
            ])
            generation = {
                "diameter_nm": truth[0],
                "n_real_formula": "2.10 + 0.45 * ((550 / wavelength_nm)^2 - 1)",
                "k_formula": "0.04 + 0.12 * exp(-((wavelength_nm - 500)/55)^2)",
                "constant_parameter_truth": None,
            }
        else:
            clean = spectrum(wavelengths, *truth)
            generation = {"constant_parameter_truth": dict(zip(PARAMETERS, truth))}
        observed = clean.copy()
        sigma = None
        if kind == "noisy":
            sigma = 0.02 * normalization_scale(clean[train])
            observed = np.maximum(0.0, clean + np.random.default_rng(20261010).normal(0.0, sigma, len(clean)))
            generation.update({"noise_seed": 20261010, "noise_sigma_qsca": sigma, "noise_distribution": "independent Gaussian, clipped at zero"})
        scenarios.append({
            "case_id": case_id, "label": label, "kind": kind, "n_env": 1.0,
            "wavelengths_nm": wavelengths.tolist(), "observed_qsca": observed.tolist(),
            "latent_qsca": clean.tolist(), "train_indices": train.tolist(),
            "holdout_indices": held.tolist(), "generation": generation,
            "scale": normalization_scale(observed[train]), "limit_nrmse": threshold,
            "noise_sigma_qsca": sigma,
        })
    return scenarios


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False), encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _contains(parent, child):
    return Path(child).resolve().is_relative_to(Path(parent).resolve())


def _check_separation(private_root, agent_workspace, store):
    private_root, agent_workspace, store = map(lambda p: Path(p).resolve(), (private_root, agent_workspace, store))
    if _contains(agent_workspace, private_root) or _contains(private_root, agent_workspace):
        raise ValueError("Private targets and agent workspace must be disjoint directories.")
    if _contains(agent_workspace, store) or _contains(store, agent_workspace):
        raise ValueError("The MCP experiment store must be outside the agent workspace.")


def _criteria(scenario):
    limit = scenario["limit_nrmse"]
    if scenario["kind"] == "mismatch":
        meaning = "Model adequacy diagnostic: <=5% held-out NRMSE supports this constant-index approximation on this grid; a miss is not evidence that the optimizer is defective. No constant n,k ground truth exists."
    elif scenario["kind"] == "noisy":
        meaning = "Observed held-out NRMSE <=6% (about three times the prescribed 2% signal-relative noise sigma). Recovering the random noise or exact parameters is not required."
    else:
        meaning = "Held-out NRMSE <=1% for spectrum recovery. Parameter errors are diagnostics only; finite spectra can admit weakly identified parameters, especially near low-contrast bounds."
    return {"holdout_nrmse_limit": limit, "interpretation": meaning}


def task_text(run_id, case_id):
    return (
        f"Nano Chameleon benchmark case {case_id}; experiment ID {run_id}. "
        "Use only the nano-chameleon MCP tools. First inspect_experiment, state the "
        "constant-index sphere model and bounds, then plan and execute at least two "
        "simulate_candidate calls. Explain how their training errors and curves inform "
        "the next decision. Call search_candidates once with generations=15 and seed=7. "
        "Design at least one subsequent simulate_candidate based on that feedback, "
        "then validate_unseen_wavelengths exactly once and export_experiment_report. "
        "Do not read source files, raw CSVs, runs/, benchmark private files, numerical "
        "baseline reports, or held-out targets. Use training data only until validation. "
        "Report measured training and held-out errors and discuss non-uniqueness, "
        "noise or model inadequacy where supported. Do not claim exact parameters from "
        "a good spectral fit alone. Keep the real AGH model/session/tool trajectory as "
        "evidence; the search_candidates tool is a physics optimizer and its calls are "
        "not separate Agnes model calls. Maximum one search (15 generations), 12 manual "
        "candidate trials, one validation, and one report export."
    )


def prepare(output_root, private_root, store, agent_workspace):
    _check_separation(private_root, agent_workspace, store)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suite_id = f"{stamp}_{uuid.uuid4().hex[:8]}"
    output_dir = Path(output_root) / suite_id
    private_dir = Path(private_root) / suite_id
    output_dir.mkdir(parents=True, exist_ok=False)
    private_dir.mkdir(parents=True, exist_ok=False)
    agent_dir = Path(agent_workspace) / suite_id
    agent_dir.mkdir(parents=True, exist_ok=False)
    scenarios = generate_scenarios()
    cases = []
    for scenario in scenarios:
        if scenario["case_id"] not in ("clean_a", "clean_b", "noisy", "mismatch"):
            continue
        rows = zip(scenario["wavelengths_nm"], scenario["observed_qsca"])
        run_id = create_experiment(store, rows, scenario["n_env"])
        cases.append({
            "case_id": scenario["case_id"], "scenario_id": scenario["case_id"],
            "name": scenario["label"], "scenario": scenario["label"],
            "run_id": run_id, "agh_run_id": run_id,
            "status": "prepared; no AGH execution claimed",
            "criteria": _criteria(scenario), "task": task_text(run_id, scenario["case_id"]),
        })
    manifest = {
        "suite_id": suite_id, "created_utc": stamp, "normalization": NORMALIZATION,
        "agent_workspace": str(agent_dir.resolve()),
        "protocol": {
            "training_samples": 35, "held_out_samples": 8,
            "split": "sorted index 2,7,12,...,37 held out; endpoints remain in training",
            "baseline": "SciPy differential_evolution physics optimizer, 15 generations, seeds 7/19/43; not AGH",
            "agent_budget": {"search_calls": 1, "generations": 15, "manual_candidates_max": 12},
            "file_access": "Use MCP only. Private targets and experiment JSON are outside this workspace; this is workflow isolation, not an OS security sandbox.",
        },
        "cases": cases,
    }
    write_json(output_dir / "agh_tasks_public.json", manifest)
    write_json(agent_dir / "agh_tasks_public.json", manifest)
    private = {
        "suite_id": suite_id, "output_dir": str(output_dir.resolve()),
        "store": str(Path(store).resolve()),
        "baseline_store": str((output_dir / "baseline_runs").resolve()),
        "scenarios": scenarios,
        "agh_cases": [{"case_id": c["case_id"], "run_id": c["run_id"]} for c in cases],
        "baseline_runs": [], "baseline_batches": [],
        "versions": {"python": platform.python_version(), "miepython": miepython.__version__, "numpy": np.__version__, "scipy": scipy.__version__},
        "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in ("engine.py", "benchmark.py")},
    }
    write_json(private_dir / "suite_private.json", private)
    return {"suite_id": suite_id, "public_manifest": str((output_dir / "agh_tasks_public.json").resolve()), "agent_manifest": str((agent_dir / "agh_tasks_public.json").resolve()), "agh_run_ids": {case["case_id"]: case["run_id"] for case in cases}}


def load_suite(suite_id, private_root):
    if not suite_id or Path(suite_id).name != suite_id or any(c not in "0123456789TZ_abcdef" for c in suite_id):
        raise ValueError("Invalid suite ID.")
    path = Path(private_root) / suite_id / "suite_private.json"
    return path, read_json(path)


def score_record(record, scenario):
    final = record["final"]
    if final is None:
        raise ValueError("Only sealed experiments can be scored.")
    if record["holdout_indices"] != scenario["holdout_indices"]:
        raise ValueError("Experiment split differs from the predefined benchmark split.")
    expected = np.column_stack((scenario["wavelengths_nm"], scenario["observed_qsca"]))
    if not np.array_equal(np.asarray(record["target"]), expected):
        raise ValueError("Experiment target differs from the prepared benchmark target.")
    scale = scenario["scale"]
    train_nrmse = final["train_rmse"] / scale
    hold_nrmse = final["holdout_rmse"] / scale
    truth = scenario["generation"]["constant_parameter_truth"]
    parameter_errors = None if truth is None else {
        name: {"absolute": abs(final["parameters"][name] - truth[name]),
               "fraction_of_search_range": abs(final["parameters"][name] - truth[name]) / (bounds[1] - bounds[0])}
        for name, bounds in zip(PARAMETERS, BOUNDS)
    }
    latent = np.asarray(scenario["latent_qsca"])
    predicted = np.asarray(final["predicted_full_curve"])
    held = scenario["holdout_indices"]
    outcome = "adequate" if hold_nrmse <= scenario["limit_nrmse"] else "inadequate"
    if scenario["kind"] != "mismatch":
        outcome = "pass" if outcome == "adequate" else "miss"
    return {
        "case_id": scenario["case_id"], "run_id": record["run_id"],
        "train_rmse": final["train_rmse"], "holdout_rmse": final["holdout_rmse"],
        "normalization_scale": scale, "train_nrmse": train_nrmse,
        "holdout_nrmse": hold_nrmse, "limit_nrmse": scenario["limit_nrmse"],
        "outcome": outcome, "parameters": final["parameters"],
        "parameter_errors": parameter_errors,
        "latent_holdout_nrmse": float(np.sqrt(np.mean((predicted[held] - latent[held]) ** 2)) / scale),
        "trial_count": len(record["trials"]),
    }


def baseline(suite_id, private_root, seeds, generations):
    seeds = tuple(seeds)
    if not 1 <= len(seeds) <= 3 or len(set(seeds)) != len(seeds):
        raise ValueError("Use one to three distinct seeds.")
    if not 10 <= generations <= 20:
        raise ValueError("Benchmark generations must be between 10 and 20.")
    private_path, suite = load_suite(suite_id, private_root)
    count = len(suite["scenarios"]) * len(seeds)
    if count > 24:
        raise ValueError("A bounded baseline batch may contain at most 24 runs.")
    batch_id = uuid.uuid4().hex[:8]
    batch = {"batch_id": batch_id, "seeds": list(seeds), "generations": generations,
             "polish": True, "popsize": 5, "planned_runs": count,
             "algorithm": "scipy.optimize.differential_evolution", "kind": "physics optimizer baseline",
             "runtime_source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in ("engine.py", "benchmark.py")}}
    suite["baseline_batches"].append(batch)
    write_json(private_path, suite)
    for scenario in suite["scenarios"]:
        for seed in seeds:
            run_id = create_experiment(suite["baseline_store"], zip(scenario["wavelengths_nm"], scenario["observed_qsca"]), scenario["n_env"])
            entry = {"case_id": scenario["case_id"], "run_id": run_id,
                     "seed": seed, "generations": generations, "batch_id": batch_id,
                     "kind": "physics optimizer baseline", "status": "running"}
            suite["baseline_runs"].append(entry)
            write_json(private_path, suite)
            start = time.perf_counter()
            optimize(suite["baseline_store"], run_id, generations=generations, seed=seed)
            finalize(suite["baseline_store"], run_id)
            entry.update(score_record(report_record(suite["baseline_store"], run_id), scenario))
            entry.update({"status": "complete", "elapsed_seconds": time.perf_counter() - start})
            write_json(private_path, suite)
            print(json.dumps({"case": scenario["case_id"], "seed": seed, "run_id": run_id,
                              "holdout_nrmse": entry["holdout_nrmse"], "outcome": entry["outcome"],
                              "completed": sum(e["status"] == "complete" for e in suite["baseline_runs"])}), flush=True)
    return {"suite_id": suite_id, "batch_id": batch_id, "completed": count}


def _format(value):
    return f"{value:.3g}"


def _figure_image(fig):
    import matplotlib.pyplot as plt
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=155, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _plots(suite, results):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    scenarios = suite["scenarios"]
    colors = {"baseline": "#227b75", "observed": "#474b50", "held": "#bd6c25", "latent": "#687aac"}
    spectra = []
    for scenario in scenarios:
        fig, ax = plt.subplots(figsize=(5.8, 3.9), constrained_layout=True)
        waves = np.asarray(scenario["wavelengths_nm"])
        observed = np.asarray(scenario["observed_qsca"])
        train, held = scenario["train_indices"], scenario["holdout_indices"]
        ax.plot(waves[train], observed[train], ".", color=colors["observed"], label="training observations", markersize=4)
        ax.scatter(waves[held], observed[held], facecolors="none", edgecolors=colors["held"], label="sealed observations", s=28)
        if scenario["kind"] == "noisy":
            ax.plot(waves, scenario["latent_qsca"], "--", color=colors["latent"], label="latent noise-free curve", linewidth=1)
        entries = [r for r in results if r["case_id"] == scenario["case_id"] and r["kind"] == "physics optimizer baseline"]
        # Selection uses training error only, never held-out performance.
        if entries:
            best = min(entries, key=lambda e: e["train_rmse"])
            record = report_record(suite["baseline_store"], best["run_id"])
            ax.plot(waves, record["final"]["predicted_full_curve"], color=colors["baseline"], label="lowest-training-error baseline", linewidth=1.6)
        for entry in (r for r in results if r["case_id"] == scenario["case_id"] and r["kind"] == "actual AGH"):
            record = report_record(suite["store"], entry["run_id"])
            ax.plot(waves, record["final"]["predicted_full_curve"], "--", color="#6f59a1", label="AGH-selected fit", linewidth=1.3)
        ax.set_title(scenario["label"], loc="left", fontsize=12)
        ax.set_xlabel("Wavelength (nm)"); ax.set_ylabel("Qsca (dimensionless)")
        ax.grid(alpha=.18)
        ax.legend(fontsize=9, frameon=False)
        ax.ticklabel_format(axis="y", style="sci", scilimits=(-3, 3))
        spectra.append({"label": scenario["label"], "image": _figure_image(fig)})
    fig, ax = plt.subplots(figsize=(10, 4.1), constrained_layout=True)
    labels = [s["label"] for s in scenarios]
    for i, scenario in enumerate(scenarios):
        entries = [r for r in results if r["case_id"] == scenario["case_id"] and r["kind"] == "physics optimizer baseline"]
        offsets = np.linspace(-.17, .17, len(entries)) if len(entries) > 1 else [0]
        for offset, entry in zip(offsets, entries):
            ax.scatter(i + offset, max(entry["holdout_nrmse"], 1e-10), color=colors["baseline"], s=35)
        ax.hlines(scenario["limit_nrmse"], i - .28, i + .28, color="#aa3c4a", linewidth=2)
        for entry in (r for r in results if r["case_id"] == scenario["case_id"] and r["kind"] == "actual AGH"):
            ax.scatter(i + .3, max(entry["holdout_nrmse"], 1e-10), color="#6f59a1", marker="D", s=40)
    ax.set_yscale("log"); ax.set_ylabel("Held-out RMSE / RMS(training signal)")
    ax.set_xticks(range(len(labels)), labels, rotation=15, ha="right", fontsize=8)
    ax.grid(axis="y", alpha=.2)
    ax.plot([], [], "o", color=colors["baseline"], label="each optimizer seed")
    ax.plot([], [], "-", color="#aa3c4a", label="predeclared criterion")
    if any(r["kind"] == "actual AGH" for r in results):
        ax.plot([], [], "D", color="#6f59a1", label="AGH-selected fit (verified trajectory)")
    ax.legend(frameon=False, loc="upper left")
    errors = _figure_image(fig)
    fig, ax = plt.subplots(figsize=(5.3, 5), constrained_layout=True)
    short_labels = ["Clean A", "Clean B", "Lower bounds", "Upper bounds", "Noisy", "Dispersive mismatch"]
    for i, scenario in enumerate(scenarios):
        entries = [r for r in results if r["case_id"] == scenario["case_id"] and r["kind"] == "physics optimizer baseline"]
        offsets = np.linspace(-.14, .14, len(entries)) if len(entries) > 1 else [0]
        for offset, entry in zip(offsets, entries):
            ax.scatter(max(entry["holdout_nrmse"], 1e-10), i + offset, color=colors["baseline"], s=35)
        ax.vlines(scenario["limit_nrmse"], i - .28, i + .28, color="#aa3c4a", linewidth=2)
        for entry in (r for r in results if r["case_id"] == scenario["case_id"] and r["kind"] == "actual AGH"):
            ax.scatter(max(entry["holdout_nrmse"], 1e-10), i + .3, color="#6f59a1", marker="D", s=40)
    ax.set_xscale("log"); ax.set_xlabel("Held-out signal-relative RMSE")
    ax.set_yticks(range(len(short_labels)), short_labels, fontsize=10)
    ax.invert_yaxis(); ax.grid(axis="x", alpha=.2)
    ax.plot([], [], "o", color=colors["baseline"], label="each optimizer seed")
    ax.plot([], [], "-", color="#aa3c4a", label="criterion")
    if any(r["kind"] == "actual AGH" for r in results):
        ax.plot([], [], "D", color="#6f59a1", label="AGH-selected fit")
    ax.legend(frameon=False, fontsize=9, loc="lower left")
    errors_mobile = _figure_image(fig)
    fig, ax = plt.subplots(figsize=(10, 4.3), constrained_layout=True)
    for scenario in scenarios:
        entries = [r for r in results if r["case_id"] == scenario["case_id"] and r["kind"] == "physics optimizer baseline"]
        if not entries:
            continue
        best = min(entries, key=lambda e: e["train_rmse"])
        record = report_record(suite["baseline_store"], best["run_id"])
        curve = np.minimum.accumulate([t["train_rmse"] / scenario["scale"] for t in record["trials"]])
        ax.plot(np.arange(1, len(curve) + 1), np.maximum(curve, 1e-12), label=scenario["label"], linewidth=1.5)
    ax.set_xlabel("Recorded candidate evaluations (includes polishing)")
    ax.set_ylabel("Best-so-far training NRMSE"); ax.set_yscale("log")
    ax.grid(alpha=.2); ax.legend(frameon=False, fontsize=8, ncols=2)
    convergence = _figure_image(fig)
    fig, ax = plt.subplots(figsize=(5.3, 4.5), constrained_layout=True)
    for short_label, scenario in zip(short_labels, scenarios):
        entries = [r for r in results if r["case_id"] == scenario["case_id"] and r["kind"] == "physics optimizer baseline"]
        if not entries:
            continue
        best = min(entries, key=lambda e: e["train_rmse"])
        record = report_record(suite["baseline_store"], best["run_id"])
        curve = np.minimum.accumulate([t["train_rmse"] / scenario["scale"] for t in record["trials"]])
        ax.plot(np.arange(1, len(curve) + 1), np.maximum(curve, 1e-12), label=short_label, linewidth=1.5)
    ax.set_xlabel("Candidate evaluations (incl. polishing)")
    ax.set_ylabel("Best training NRMSE"); ax.set_yscale("log")
    ax.grid(alpha=.2); ax.legend(frameon=False, fontsize=9, ncols=2)
    convergence_mobile = _figure_image(fig)
    return spectra, errors, errors_mobile, convergence, convergence_mobile


def load_agh_evidence(path, suite):
    if path is None:
        return {}
    entries = read_json(path)
    if not isinstance(entries, list):
        raise ValueError("AGH evidence manifest must be a top-level list.")
    allowed = {c["run_id"]: c["case_id"] for c in suite["agh_cases"]}
    found = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("run_id") not in allowed:
            raise ValueError("AGH evidence contains an unknown experiment ID.")
        run_id = entry["run_id"]
        if run_id in found or entry.get("scenario_id") != allowed[run_id]:
            raise ValueError("AGH evidence has a duplicate run or wrong scenario.")
        if not isinstance(entry.get("complete"), bool):
            raise ValueError("AGH evidence complete must be an explicit boolean.")
        entry = dict(entry)
        if entry.get("evidence_path"):
            evidence_path = Path(entry["evidence_path"])
            if not evidence_path.is_absolute():
                evidence_path = Path(path).resolve().parent / evidence_path
            entry["evidence_path"] = str(evidence_path.resolve())
        if entry["complete"]:
            if not entry.get("model") or not entry.get("session_id") or not entry.get("evidence_path"):
                raise ValueError("Complete AGH evidence needs model, session_id and evidence_path.")
            if not Path(entry["evidence_path"]).is_file():
                raise ValueError("Complete AGH evidence file is missing.")
            trajectory = read_json(entry["evidence_path"])
            valid, reason = audit_trajectory(trajectory, run_id)
            if not valid or trajectory.get("session_id") != entry["session_id"] or set(trajectory.get("models", [])) != set(entry["model"].split(", ")):
                raise ValueError(f"Complete AGH trajectory failed audit: {reason}")
        found[run_id] = entry
    return found


def summarize(suite_id, private_root, agh_evidence=None):
    private_path, suite = load_suite(suite_id, private_root)
    if agh_evidence is not None:
        suite["agh_evidence_file"] = str(Path(agh_evidence).resolve())
    evidence = load_agh_evidence(suite.get("agh_evidence_file"), suite)
    scenarios = {s["case_id"]: s for s in suite["scenarios"]}
    results = [dict(e) for e in suite["baseline_runs"] if e["status"] == "complete"]
    agh_statuses = []
    for case in suite["agh_cases"]:
        status = public_status(suite["store"], case["run_id"])
        supplied = evidence.get(case["run_id"], {})
        verified = bool(supplied.get("complete") and status["sealed"])
        agh_statuses.append({"case_id": case["case_id"], "run_id": case["run_id"],
                             "sealed": status["sealed"], "trial_count": status["trial_count"],
                             "protocol_complete": verified, "evidence": supplied})
        if status["sealed"]:
            result = score_record(report_record(suite["store"], case["run_id"]), scenarios[case["case_id"]])
            # A sealed run alone cannot establish an actual AGH execution.
            result.update({"kind": "actual AGH" if verified else "AGH-designated experiment (trajectory not verified)",
                           "seed": None, "status": "complete", "protocol_complete": verified,
                           "model": supplied.get("model"), "session_id": supplied.get("session_id")})
            results.append(result)
    output_dir = Path(suite["output_dir"])
    summary = {"suite_id": suite_id, "normalization": NORMALIZATION,
               "versions": suite["versions"], "source_sha256": suite["source_sha256"],
               "baseline_batches": suite["baseline_batches"], "results": results,
               "agh_statuses": agh_statuses,
               "criteria": {k: _criteria(s) for k, s in scenarios.items()}}
    write_json(output_dir / "benchmark_summary.json", summary)
    spectra, errors, errors_mobile, convergence, convergence_mobile = _plots(suite, results)
    spectra_html = ''.join(f'<figure><img src="{item["image"]}" alt="{html.escape(item["label"])}: observed training and held-out spectra with the numerical and verified AGH fits"></figure>' for item in spectra)
    rows = []
    for result in results:
        p = result["parameters"]
        rows.append("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in (
            scenarios[result["case_id"]]["label"], result["kind"], result.get("seed", ""),
            _format(result["train_nrmse"]), _format(result["holdout_nrmse"]),
            result["outcome"], result["trial_count"],
            f"{p['diameter_nm']:.3f} / {p['n_real']:.5f} / {p['k']:.5f}",
        )) + "</tr>")
    aggregates = []
    for scenario in suite["scenarios"]:
        entries = [e for e in results if e["case_id"] == scenario["case_id"] and e["kind"] == "physics optimizer baseline"]
        if entries:
            metrics = [e["holdout_nrmse"] for e in entries]
            met = sum(e["holdout_nrmse"] <= scenario["limit_nrmse"] for e in entries)
            aggregates.append(f"<tr><td>{html.escape(scenario['label'])}</td><td>{met}/{len(entries)}</td><td>{_format(float(np.median(metrics)))}</td><td>{_format(min(metrics))} to {_format(max(metrics))}</td><td>{scenario['limit_nrmse']:.0%}</td></tr>")
    sealed_count = sum(s["sealed"] for s in agh_statuses)
    verified_count = sum(s["protocol_complete"] for s in agh_statuses)
    agh_rows = []
    for status in agh_statuses:
        supplied = status["evidence"]
        fit = next((r for r in results if r["run_id"] == status["run_id"]), None)
        link = "pending"
        if supplied.get("evidence_path"):
            path = Path(supplied["evidence_path"])
            if path.is_relative_to(output_dir):
                relative = path.relative_to(output_dir).as_posix()
                link = f'<a href="{html.escape(relative, quote=True)}">native trajectory</a>'
            else:
                link = html.escape(str(path))
        values = [scenarios[status["case_id"]]["label"], supplied.get("model") or "not established",
                  supplied.get("session_id") or "not established",
                  "complete" if status["protocol_complete"] else "incomplete / unverified",
                  f'{_format(fit["holdout_nrmse"])} ({fit["outcome"]})' if fit else "not validated"]
        agh_rows.append("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in values) + f"<td>{link}</td></tr>")
    complete = sum(e["kind"] == "physics optimizer baseline" for e in results)
    all_trials = sum(e["trial_count"] for e in results if e["kind"] == "physics optimizer baseline")
    dataset_hash = hashlib.sha256(json.dumps(suite["scenarios"], sort_keys=True).encode()).hexdigest()
    limitations = (
        "This benchmark uses synthetic Mie efficiencies, not measurements of real materials. "
        "The holdout consists of interleaved wavelengths on the same grid, so it tests interpolation, "
        "not extrapolation or transfer to different particles. No confidence interval or statistical "
        "significance claim is supported by three seeds. Spectral agreement alone does not prove "
        "unique parameter recovery. Noise and dispersion were generated before search. The "
        "mismatch criterion assesses model adequacy, not exact recovery. All scores and seed "
        "outcomes are retained, including misses."
    )
    report = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nano Chameleon benchmark report</title><style>
:root {{font-family: system-ui, sans-serif; color:#252b30; background:#fff; color-scheme:light}} * {{box-sizing:border-box}} body{{margin:0}} main{{max-width:1160px;margin:auto;padding:32px 28px 60px}} header{{border-bottom:2px solid #237d75;padding-bottom:18px}} h1{{font-size:28px;margin:0 0 12px}} h2{{font-size:20px;margin:32px 0 12px}} h3{{font-size:16px;margin:20px 0 10px}} p,li{{line-height:1.55;font-size:14px}} .meta{{color:#58636a;font-size:12px;overflow-wrap:anywhere}} .facts{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;padding:20px 0;border-bottom:1px solid #dce2e4}} .facts span{{display:block;font-size:12px;color:#58636a;margin-bottom:5px}} .facts strong{{font-size:22px;font-variant-numeric:tabular-nums}} .table-wrap{{overflow-x:auto}} table{{width:100%;border-collapse:collapse;font-size:12px}} th,td{{text-align:left;padding:9px;border-bottom:1px solid #dce2e4;vertical-align:top}} th{{background:#eef3f2;font-weight:600}} td{{font-variant-numeric:tabular-nums}} figure{{margin:16px 0}} img{{display:block;width:100%;height:auto}} figcaption{{font-size:12px;color:#58636a;line-height:1.5;margin-top:9px}} code{{font-size:12px;overflow-wrap:anywhere}} .status{{border-left:3px solid #966732;padding-left:14px}} .spectra-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 18px}} @media(max-width:650px){{main{{padding:22px 14px 40px}}h1{{font-size:24px}}.facts{{grid-template-columns:repeat(2,minmax(0,1fr))}}.spectra-grid{{grid-template-columns:minmax(0,1fr)}}th,td{{padding:7px}}}}
</style></head><body><main><header><h1>Nano Chameleon benchmark</h1><p>Inverse Mie scattering with a sealed wavelength holdout</p><p class="meta">Suite {html.escape(suite_id)}. Deterministic synthetic datasets; bounded optimizer seeds; distinct AGH experiments.</p></header>
<div class="facts"><div><span>Scenarios</span><strong>6</strong></div><div><span>Completed optimizer runs</span><strong>{complete}</strong></div><div><span>Candidate evaluations</span><strong>{all_trials:,}</strong></div><div><span>Verified AGH protocols</span><strong>{verified_count}/4</strong></div></div>
<h2>Execution status and interpretation</h2><p class="status">The {complete} completed numerical runs are SciPy physics optimizer baselines. The four AGH-designated experiments have {sealed_count} sealed results and {verified_count} complete native trajectories supplied by the AGH controller. A complete protocol requires model/session evidence, ordered candidate and search calls, validation and report export. Agent protocol completion and spectrum-fit criteria are reported separately; a completed AGH task can still produce an inadequate physical model.</p>
<div class="table-wrap"><table><thead><tr><th>AGH scenario</th><th>Model</th><th>Session</th><th>Protocol status</th><th>Held-out NRMSE and fit outcome</th><th>Evidence</th></tr></thead><tbody>{''.join(agh_rows)}</tbody></table></div>
<p>Each scenario contains 43 wavelengths from 390 to 810 nm, with 35 training and 8 held-out samples. The held-out indices are 2, 7, 12, 17, 22, 27, 32 and 37 in the sorted grid. The split and targets are identical across seeds and designated AGH runs. Parameters are constrained to diameter 50 to 500 nm, real index 1.05 to 2.8, and absorption index 0 to 0.35; the environment index is 1.</p>
<p>Normalized error is <strong>RMSE / RMS(observed training Qsca)</strong>, with a denominator floor of 1e-8. This signal-relative metric makes the weak lower-bound spectrum comparable to high-scattering cases; an absolute error alone could make a near-zero signal look deceptively accurate. The denominator uses training observations only.</p>
<h2>Predeclared scenario criteria</h2><ul>{''.join(f'<li><strong>{html.escape(s["label"])}</strong>: {html.escape(_criteria(s)["interpretation"])}</li>' for s in suite['scenarios'])}</ul>
<p>The noisy data use independent Gaussian noise with sigma equal to 2% of the latent training signal RMS, seed 20261010, followed by clipping at zero. Model mismatch uses a wavelength-dependent index and absorption peak, fitted using a constant n and k sphere. The generator parameters are retained privately; AGH task manifests exclude them.</p>
<h2>Seed robustness</h2><div class="table-wrap"><table><thead><tr><th>Scenario</th><th>Criterion met</th><th>Median held-out NRMSE</th><th>Range across seeds</th><th>Criterion</th></tr></thead><tbody>{''.join(aggregates)}</tbody></table></div>
<figure><picture><source media="(max-width:650px)" srcset="{errors_mobile}"><img src="{errors}" alt="Held-out normalized error for each numerical optimizer seed and the criterion of every scenario"></picture><figcaption>Each teal dot is one completed physics optimizer run; purple diamonds, when present, are AGH-selected fits backed by complete trajectories. Red segments show the criterion set before fitting. The error axis is logarithmic; values below 1e-10 are displayed at 1e-10. No best held-out seed is selected to represent performance.</figcaption></figure>
<h2>Spectrum reconstruction</h2><div class="spectra-grid">{spectra_html}</div><p class="meta">For each scenario the solid fit curve is selected only by lowest training RMSE across completed optimizer seeds. Verified AGH fits, when present, use purple dashed curves. Orange open circles are held-out observations. The latent noise-free curve in the noisy case was not available to fitting. Qsca is dimensionless.</p>
<h2>Search trace</h2><figure><picture><source media="(max-width:650px)" srcset="{convergence_mobile}"><img src="{convergence}" alt="Recorded best training normalized error as candidate evaluations progress"></picture><figcaption>Best-so-far training error from the same training-selected optimizer run shown above. Evaluation counts include SciPy polishing; 15 generations is not a limit of 15 candidate calls. Every recorded trial is preserved in the experiment store.</figcaption></figure>
<h2>Every completed run</h2><div class="table-wrap"><table><thead><tr><th>Scenario</th><th>Executor</th><th>Seed</th><th>Train NRMSE</th><th>Held-out NRMSE</th><th>Outcome</th><th>Trials</th><th>Recovered diameter / n / k</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<h2>Reproducibility and limits</h2><p>{html.escape(limitations)}</p><p>Baseline batches: <code>{html.escape(json.dumps(suite['baseline_batches']))}</code>. Dependency versions: <code>{html.escape(json.dumps(suite['versions']))}</code>.</p><p class="meta">Generator dataset SHA-256: {dataset_hash}<br>Source hashes: {html.escape(json.dumps(suite['source_sha256']))}</p><p>Public manifest: <a href="agh_tasks_public.json">agh_tasks_public.json</a>. Machine-readable result table: <a href="benchmark_summary.json">benchmark_summary.json</a>. The JSON summary contains recovered parameters and diagnostics; it must remain outside an active AGH task workspace.</p>
</main></body></html>"""
    path = output_dir / "benchmark_report.html"
    path.write_text(report, encoding="utf-8")
    # Keep every suite report while also exposing a convenient latest deliverable.
    latest_report = report.replace('href="agh_tasks_public.json"', f'href="benchmarks/{suite_id}/agh_tasks_public.json"').replace('href="benchmark_summary.json"', f'href="benchmarks/{suite_id}/benchmark_summary.json"')
    for status in agh_statuses:
        supplied = status["evidence"]
        if supplied.get("evidence_path") and Path(supplied["evidence_path"]).is_relative_to(output_dir):
            relative = Path(supplied["evidence_path"]).relative_to(output_dir).as_posix()
            latest_report = latest_report.replace(f'href="{html.escape(relative, quote=True)}"', f'href="benchmarks/{suite_id}/{html.escape(relative, quote=True)}"')
    (ROOT / "benchmark_report.html").write_text(latest_report, encoding="utf-8")
    write_json(private_path, suite)
    return {"report": str(path.resolve()), "latest_report": str((ROOT / "benchmark_report.html").resolve()), "summary": str((output_dir / "benchmark_summary.json").resolve()), "completed_baselines": complete, "agh_sealed": sealed_count, "verified_agh": verified_count}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, default=DEFAULT_PRIVATE)
    actions = parser.add_subparsers(dest="action", required=True)
    command = actions.add_parser("prepare", help="Generate private targets and four sealed AGH tasks")
    command.add_argument("--output-root", type=Path, default=ROOT / "benchmarks")
    command.add_argument("--store", type=Path, default=ROOT / "runs")
    command.add_argument("--agent-workspace", type=Path, default=DEFAULT_AGENT_WORKSPACE)
    command = actions.add_parser("baseline", help="Run bounded physics optimizer comparisons; preserves old runs")
    command.add_argument("suite_id")
    command.add_argument("--seeds", nargs="+", type=int, default=list(DEFAULT_SEEDS))
    command.add_argument("--generations", type=int, default=15)
    command = actions.add_parser("summarize", help="Generate self-contained benchmark report from sealed results")
    command.add_argument("suite_id")
    command.add_argument("--agh-evidence", type=Path, help="Controller-verified native trajectory manifest; complete flags assert tool order and report export")
    args = parser.parse_args()
    if args.action == "prepare":
        result = prepare(args.output_root, args.private_root, args.store, args.agent_workspace)
    elif args.action == "baseline":
        result = baseline(args.suite_id, args.private_root, args.seeds, args.generations)
    else:
        result = summarize(args.suite_id, args.private_root, args.agh_evidence)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()

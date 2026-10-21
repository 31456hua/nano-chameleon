"""Reproducible Mie-spectrum inversion with a sealed wavelength holdout."""

from __future__ import annotations

import csv
import json
import math
from numbers import Integral
import os
import threading
import uuid
from pathlib import Path

import miepython
import numpy as np
from scipy.optimize import differential_evolution


BOUNDS = ((50.0, 500.0), (1.05, 2.8), (0.0, 0.35))
_LOCK = threading.RLock()


def spectrum(wavelengths_nm, diameter_nm, n_real, k, n_env=1.0):
    """Return dimensionless scattering efficiency Qsca for a sphere."""
    values = (diameter_nm, n_real, k, n_env)
    if not all(math.isfinite(float(x)) for x in values):
        raise ValueError("Particle and medium parameters must be finite.")
    for value, (lower, upper), name in zip(
        values[:3], BOUNDS, ("diameter_nm", "n_real", "k")
    ):
        if not lower <= value <= upper:
            raise ValueError(f"{name} must be between {lower} and {upper}.")
    if not 1.0 <= n_env <= 2.0:
        raise ValueError("n_env must be between 1.0 and 2.0.")
    wavelengths = np.asarray(wavelengths_nm, dtype=float)
    if wavelengths.ndim != 1 or len(wavelengths) == 0:
        raise ValueError("Wavelengths must be a nonempty one-dimensional array.")
    if not np.all(np.isfinite(wavelengths)) or np.any(wavelengths <= 0):
        raise ValueError("Wavelengths must be finite and positive.")
    # miepython uses n - i*k for an absorbing particle.
    _, qsca, _, _ = miepython.efficiencies(
        complex(n_real, -k), diameter_nm, wavelengths, n_env=n_env
    )
    qsca = np.atleast_1d(np.asarray(qsca, dtype=float))
    if not np.all(np.isfinite(qsca)) or np.any(qsca < 0):
        raise ValueError("Simulation returned invalid Qsca values.")
    return qsca


def _rmse(predicted, observed):
    residual = np.asarray(predicted, dtype=float) - np.asarray(observed, dtype=float)
    if not np.all(np.isfinite(residual)):
        raise ValueError("Simulation residuals must be finite.")
    # Scale before squaring so large, finite measurements do not overflow.
    scale = float(np.max(np.abs(residual)))
    return scale * float(np.sqrt(np.mean((residual / scale) ** 2))) if scale else 0.0


def read_target_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or not {"wavelength_nm", "qsca"}.issubset(reader.fieldnames):
            raise ValueError("CSV needs wavelength_nm and qsca columns.")
        rows = [(float(row["wavelength_nm"]), float(row["qsca"])) for row in reader]
    return validate_rows(rows)


def validate_rows(rows):
    rows = list(rows)
    if not 15 <= len(rows) <= 400:
        raise ValueError("Provide 15 to 400 wavelength samples.")
    rows = sorted((float(w), float(q)) for w, q in rows)
    wavelengths = np.asarray([row[0] for row in rows])
    qsca = np.asarray([row[1] for row in rows])
    if not np.all(np.isfinite(wavelengths)) or np.any(wavelengths <= 0):
        raise ValueError("All wavelengths must be finite and positive.")
    if np.any(np.diff(wavelengths) <= 0):
        raise ValueError("Wavelengths must be unique.")
    if not np.all(np.isfinite(qsca)) or np.any(qsca < 0):
        raise ValueError("All Qsca values must be finite and nonnegative.")
    return list(zip(wavelengths.tolist(), qsca.tolist()))


def _path(store, run_id):
    if not isinstance(run_id, str) or len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id):
        raise ValueError("Invalid experiment ID.")
    return Path(store) / f"{run_id}.json"


def _save(store, record):
    path = _path(store, record["run_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _load(store, run_id):
    path = _path(store, run_id)
    if not path.is_file():
        raise ValueError("Experiment ID not found.")
    return json.loads(path.read_text(encoding="utf-8"))


def create_experiment(store, rows, n_env=1.0):
    rows = validate_rows(rows)
    if not math.isfinite(n_env) or not 1.0 <= n_env <= 2.0:
        raise ValueError("n_env must be between 1.0 and 2.0.")
    # Fixed before search; both ends remain in training to avoid extrapolation.
    holdout = list(range(2, len(rows) - 1, 5))
    record = {
        "run_id": uuid.uuid4().hex,
        "model": "homogeneous sphere; wavelength-independent n and k",
        "n_env": float(n_env),
        "target": [[w, q] for w, q in rows],
        "holdout_indices": holdout,
        "trials": [],
        "final": None,
    }
    with _LOCK:
        _save(store, record)
    return record["run_id"]


def public_status(store, run_id):
    with _LOCK:
        record = _load(store, run_id)
    hidden = set(record["holdout_indices"])
    training = [
        {"wavelength_nm": w, "qsca": q}
        for i, (w, q) in enumerate(record["target"])
        if i not in hidden
    ]
    result = {
        "run_id": run_id,
        "model": record["model"],
        "n_env": record["n_env"],
        "bounds": {name: list(bounds) for name, bounds in zip(("diameter_nm", "n_real", "k"), BOUNDS)},
        "training": training,
        "holdout_count": len(hidden),
        "trial_count": len(record["trials"]),
        "best_trial": min(record["trials"], key=lambda t: t["train_rmse"]) if record["trials"] else None,
        "sealed": record["final"] is not None,
    }
    if record["final"] is not None:
        result["final"] = record["final"]
    return result


def run_trial(store, run_id, diameter_nm, n_real, k):
    with _LOCK:
        record = _load(store, run_id)
        if record["final"] is not None:
            raise ValueError("Experiment is sealed after validation; create a new run.")
        hidden = set(record["holdout_indices"])
        training = [pair for i, pair in enumerate(record["target"]) if i not in hidden]
        wavelengths = [pair[0] for pair in training]
        observed = np.asarray([pair[1] for pair in training])
        predicted = spectrum(wavelengths, diameter_nm, n_real, k, record["n_env"])
        rmse = _rmse(predicted, observed)
        trial = {
            "trial": len(record["trials"]) + 1,
            "diameter_nm": float(diameter_nm),
            "n_real": float(n_real),
            "k": float(k),
            "train_rmse": rmse,
            "curve": predicted.tolist(),
        }
        record["trials"].append(trial)
        _save(store, record)
    return trial


def optimize(store, run_id, generations=10, seed=7):
    if isinstance(generations, bool) or not isinstance(generations, Integral) or not 1 <= generations <= 30:
        raise ValueError("generations must be an integer between 1 and 30.")
    if public_status(store, run_id)["sealed"]:
        raise ValueError("Experiment is already sealed.")

    def objective(parameters):
        return run_trial(store, run_id, *map(float, parameters))["train_rmse"]

    differential_evolution(
        objective, BOUNDS, maxiter=generations, popsize=5, seed=seed,
        polish=True, updating="immediate", workers=1, tol=0,
    )
    return public_status(store, run_id)["best_trial"]


def finalize(store, run_id):
    with _LOCK:
        record = _load(store, run_id)
        if record["final"] is not None:
            return record["final"]
        if not record["trials"]:
            raise ValueError("Run at least one trial before validation.")
        best = min(record["trials"], key=lambda t: t["train_rmse"])
        wavelengths = [pair[0] for pair in record["target"]]
        predicted = spectrum(
            wavelengths, best["diameter_nm"], best["n_real"], best["k"], record["n_env"]
        )
        held = record["holdout_indices"]
        observed = np.asarray([record["target"][i][1] for i in held])
        rmse = _rmse(predicted[held], observed)
        record["final"] = {
            "best_trial": best["trial"],
            "parameters": {key: best[key] for key in ("diameter_nm", "n_real", "k")},
            "train_rmse": best["train_rmse"],
            "holdout_rmse": rmse,
            "holdout": [
                {"wavelength_nm": wavelengths[i], "observed_qsca": float(observed[j]), "predicted_qsca": float(predicted[i])}
                for j, i in enumerate(held)
            ],
            "predicted_full_curve": predicted.tolist(),
        }
        _save(store, record)
        return record["final"]


def report_record(store, run_id):
    """Read the complete record for local reporting only, after validation."""
    record = _load(store, run_id)
    if record["final"] is None:
        raise ValueError("Validate before creating a full report.")
    return record

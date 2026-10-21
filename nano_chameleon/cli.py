"""Command line workflow for the Nano Chameleon experiment."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from engine import (
    create_experiment, finalize, optimize, public_status, read_target_csv,
    report_record, run_trial, spectrum,
)
from report import write_report


ROOT = Path(__file__).resolve().parent
DEFAULT_STORE = ROOT / "runs"


def main():
    parser = argparse.ArgumentParser(description="Mie-spectrum inverse design and blind validation")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    actions = parser.add_subparsers(dest="action", required=True)
    prepare = actions.add_parser("prepare", help="Load a target CSV and seal holdout samples")
    prepare.add_argument("csv", type=Path)
    prepare.add_argument("--n-env", type=float, default=1.0)
    demo = actions.add_parser("demo", help="Generate a synthetic target, fit it, and write a report")
    demo.add_argument("--generations", type=int, default=20)
    fit = actions.add_parser("fit", help="Run the reproducible optimizer baseline")
    fit.add_argument("run_id")
    fit.add_argument("--generations", type=int, default=10)
    fit.add_argument("--seed", type=int, default=7)
    trial = actions.add_parser("trial", help="Perform one sphere simulation")
    trial.add_argument("run_id")
    trial.add_argument("diameter_nm", type=float)
    trial.add_argument("n_real", type=float)
    trial.add_argument("k", type=float)
    for action in ("status", "validate", "report"):
        command = actions.add_parser(action)
        command.add_argument("run_id")
    args = parser.parse_args()
    store = args.store

    if args.action == "prepare":
        run_id = create_experiment(store, read_target_csv(args.csv), args.n_env)
        result = public_status(store, run_id)
    elif args.action == "demo":
        wavelengths = np.linspace(400, 760, 37)
        target = spectrum(wavelengths, 260.0, 2.35, 0.015)
        sample = ROOT / "example_target.csv"
        with sample.open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow(("wavelength_nm", "qsca"))
            writer.writerows(zip(wavelengths, target))
        run_id = create_experiment(store, zip(wavelengths, target))
        optimize(store, run_id, generations=args.generations)
        finalize(store, run_id)
        result = {"run_id": run_id, "example_target_csv": str(sample), "report": str(write_report(report_record(store, run_id), ROOT / "reports"))}
        validation = public_status(store, run_id)["final"]
        result["validation"] = {key: validation[key] for key in ("parameters", "train_rmse", "holdout_rmse")}
    elif args.action == "fit":
        result = optimize(store, args.run_id, args.generations, args.seed)
    elif args.action == "trial":
        result = run_trial(store, args.run_id, args.diameter_nm, args.n_real, args.k)
    elif args.action == "status":
        result = public_status(store, args.run_id)
    elif args.action == "validate":
        result = finalize(store, args.run_id)
    else:
        result = {"report": str(write_report(report_record(store, args.run_id), ROOT / "reports"))}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


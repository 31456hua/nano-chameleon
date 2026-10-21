"""Boundary and failure checks for unattended scientific experiment batches."""

import csv
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from engine import (
    create_experiment, finalize, optimize, public_status, read_target_csv,
    report_record, run_trial, spectrum, validate_rows,
)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = Path(self.temporary.name) / "runs"
        self.rows = [(400 + 10 * index, 0.1 + index / 100) for index in range(21)]

    def write_csv(self, rows, headers=("wavelength_nm", "qsca")):
        path = Path(self.temporary.name) / "target.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(headers)
            writer.writerows(rows)
        return path

    def create_run(self, rows=None):
        return create_experiment(self.store, self.rows if rows is None else rows)

    def test_csv_rejects_invalid_values_without_creating_experiment(self):
        for column, invalid in (
            (0, "nan"), (0, "inf"), (0, "-inf"), (0, 0), (0, -1),
            (1, "nan"), (1, "inf"), (1, "-inf"), (1, -0.1),
            (0, ""), (1, "not-a-number"),
        ):
            with self.subTest(column=column, invalid=invalid):
                rows = [list(row) for row in self.rows]
                rows[4][column] = invalid
                with self.assertRaises(ValueError):
                    self.create_run(read_target_csv(self.write_csv(rows)))
                self.assertFalse(self.store.exists())

    def test_csv_requires_named_columns(self):
        with self.assertRaises(ValueError):
            read_target_csv(self.write_csv(self.rows, ("wavelength", "intensity")))

    def test_duplicate_wavelengths_rejected_even_when_unsorted(self):
        rows = list(reversed(self.rows))
        rows[7] = (rows[1][0], 0.3)
        with self.assertRaises(ValueError):
            read_target_csv(self.write_csv(rows))

    def test_sample_count_and_sorted_order(self):
        for count in (14, 401):
            with self.subTest(count=count), self.assertRaises(ValueError):
                validate_rows((400 + index, 0.1) for index in range(count))
        for count in (15, 400):
            with self.subTest(count=count):
                rows = [(400 + index, 0.1) for index in range(count)]
                self.assertEqual(validate_rows(reversed(rows)), rows)

    def test_spectrum_rejects_nonfinite_and_out_of_bounds_parameters(self):
        valid = [260.0, 2.35, 0.015, 1.0]
        cases = (
            (0, float("nan")), (1, float("inf")), (2, float("-inf")),
            (3, float("nan")), (0, 49.9), (0, 500.1),
            (1, 1.049), (1, 2.801), (2, -0.001), (2, 0.351),
            (3, 0.999), (3, 2.001),
        )
        for index, value in cases:
            with self.subTest(index=index, value=value):
                parameters = valid.copy()
                parameters[index] = value
                with self.assertRaises(ValueError):
                    spectrum([400, 500], *parameters)

    def test_spectrum_rejects_invalid_wavelength_arrays(self):
        for wavelengths in ([], [[400, 500]], [0], [-1], [float("nan")], [float("inf")]):
            with self.subTest(wavelengths=wavelengths), self.assertRaises(ValueError):
                spectrum(wavelengths, 260, 2.35, 0.015)

    def test_create_rejects_invalid_medium_without_writing(self):
        for medium in (float("nan"), float("inf"), float("-inf"), 0.99, 2.01):
            with self.subTest(medium=medium), self.assertRaises(ValueError):
                create_experiment(self.store, self.rows, n_env=medium)
            self.assertFalse(self.store.exists())

    def test_invalid_trial_does_not_mutate_record(self):
        run_id = self.create_run()
        path = self.store / (run_id + ".json")
        before = path.read_bytes()
        with self.assertRaises(ValueError):
            run_trial(self.store, run_id, float("nan"), 2.35, 0.015)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(public_status(self.store, run_id)["trial_count"], 0)

    def test_invalid_ids_cannot_select_external_paths(self):
        for run_id in ("../target", "g" * 32, "A" * 32, "0" * 31, None):
            with self.subTest(run_id=run_id), self.assertRaises(ValueError):
                public_status(self.store, run_id)

    def test_validation_requires_trial_and_report_requires_validation(self):
        run_id = self.create_run()
        with self.assertRaises(ValueError):
            finalize(self.store, run_id)
        with self.assertRaises(ValueError):
            report_record(self.store, run_id)
        self.assertFalse(public_status(self.store, run_id)["sealed"])

    def test_holdout_is_hidden_then_finalization_is_idempotent_and_sealed(self):
        wavelengths = np.asarray([row[0] for row in self.rows])
        target = spectrum(wavelengths, 260, 2.35, 0.015)
        run_id = self.create_run(zip(wavelengths, target))
        status = public_status(self.store, run_id)
        held = set(wavelengths[2:-1:5].tolist())
        self.assertTrue(held.isdisjoint(point["wavelength_nm"] for point in status["training"]))
        self.assertNotIn("target", status)
        self.assertNotIn("final", status)
        run_trial(self.store, run_id, 260, 2.35, 0.015)
        result = finalize(self.store, run_id)
        path = self.store / (run_id + ".json")
        before = path.read_bytes()
        self.assertEqual(finalize(self.store, run_id), result)
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaises(ValueError):
            run_trial(self.store, run_id, 261, 2.35, 0.015)
        with patch("engine.differential_evolution") as solver:
            with self.assertRaises(ValueError):
                optimize(self.store, run_id, generations=1)
            solver.assert_not_called()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(public_status(self.store, run_id)["trial_count"], 1)
        self.assertEqual(set(point["wavelength_nm"] for point in result["holdout"]), held)

    def test_optimizer_forwards_bounded_generations_and_serial_execution(self):
        for generations in (1, 30):
            with self.subTest(generations=generations):
                run_id = self.create_run()
                with patch("engine.differential_evolution") as solver:
                    solver.side_effect = lambda objective, *args, **kwargs: objective((260, 2.35, 0.015))
                    best = optimize(self.store, run_id, generations=generations, seed=19)
                    kwargs = solver.call_args.kwargs
                self.assertEqual(kwargs["maxiter"], generations)
                self.assertEqual(kwargs["workers"], 1)
                self.assertEqual(kwargs["seed"], 19)
                self.assertEqual(best["trial"], 1)

    def test_optimizer_rejects_out_of_range_generations_before_solver(self):
        run_id = self.create_run()
        for generations in (0, 31, -1, float("nan"), float("inf")):
            with self.subTest(generations=generations):
                with patch("engine.differential_evolution") as solver:
                    with self.assertRaises(ValueError):
                        optimize(self.store, run_id, generations=generations)
                    solver.assert_not_called()
        self.assertEqual(public_status(self.store, run_id)["trial_count"], 0)

    def test_optimizer_rejects_fractional_and_boolean_generations_before_solver(self):
        run_id = self.create_run()
        for generations in (1.5, True):
            with self.subTest(generations=generations):
                with patch("engine.differential_evolution") as solver:
                    with self.assertRaises(ValueError):
                        optimize(self.store, run_id, generations=generations)
                    solver.assert_not_called()

    def test_nonfinite_solver_output_rejected_without_recording(self):
        run_id = self.create_run()
        before = (self.store / (run_id + ".json")).read_bytes()
        invalid_output = np.full(17, float("nan"))
        with patch("engine.miepython.efficiencies", return_value=(None, invalid_output, None, None)):
            with self.assertRaises(ValueError):
                run_trial(self.store, run_id, 260, 2.35, 0.015)
        self.assertEqual((self.store / (run_id + ".json")).read_bytes(), before)

    def test_large_finite_target_has_finite_rmse_and_strict_json(self):
        run_id = self.create_run((wavelength, 1e308) for wavelength, _ in self.rows)
        with np.errstate(over="ignore", invalid="ignore"):
            trial = run_trial(self.store, run_id, 260, 2.35, 0.015)
            result = finalize(self.store, run_id)
        self.assertTrue(math.isfinite(trial["train_rmse"]))
        self.assertTrue(math.isfinite(result["holdout_rmse"]))
        self.assertEqual(trial["train_rmse"], 1e308)
        def reject_constant(value):
            raise ValueError("Invalid JSON constant: " + value)
        record = json.loads(
            (self.store / (run_id + ".json")).read_text(encoding="utf-8"),
            parse_constant=reject_constant,
        )
        self.assertEqual(record["final"]["holdout_rmse"], 1e308)


if __name__ == "__main__":
    unittest.main()

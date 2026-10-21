"""Focused checks for the experiment boundary and inverse solver."""

import tempfile
import unittest

import numpy as np

from engine import create_experiment, finalize, optimize, public_status, run_trial, spectrum


class ExperimentTests(unittest.TestCase):
    def test_holdout_is_hidden_and_seals_after_validation(self):
        with tempfile.TemporaryDirectory() as store:
            wavelengths = np.linspace(400, 760, 21)
            qsca = spectrum(wavelengths, 260, 2.35, 0.015)
            run_id = create_experiment(store, zip(wavelengths, qsca))
            before = public_status(store, run_id)
            self.assertEqual(len(before["training"]), 17)
            self.assertEqual(before["holdout_count"], 4)
            trial = run_trial(store, run_id, 260, 2.35, 0.015)
            self.assertEqual(len(trial["curve"]), 17)
            self.assertLess(trial["train_rmse"], 1e-12)
            result = finalize(store, run_id)
            self.assertLess(result["holdout_rmse"], 1e-12)
            with self.assertRaises(ValueError):
                run_trial(store, run_id, 261, 2.35, 0.015)

    def test_optimizer_recovers_resonant_synthetic_target(self):
        with tempfile.TemporaryDirectory() as store:
            wavelengths = np.linspace(400, 760, 37)
            qsca = spectrum(wavelengths, 260, 2.35, 0.015)
            run_id = create_experiment(store, zip(wavelengths, qsca))
            best = optimize(store, run_id, generations=20, seed=7)
            result = finalize(store, run_id)
            self.assertGreater(public_status(store, run_id)["trial_count"], 20)
            self.assertLess(best["train_rmse"], 1e-4)
            self.assertLess(result["holdout_rmse"], 1e-4)


if __name__ == "__main__":
    unittest.main()


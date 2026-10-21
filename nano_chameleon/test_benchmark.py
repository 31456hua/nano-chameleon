"""Focused checks for benchmark determinism, isolation and honest scoring."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

import benchmark
from engine import create_experiment, finalize, report_record, run_trial


class BenchmarkTests(unittest.TestCase):
    def test_scenarios_are_deterministic_and_use_exact_engine_split(self):
        first, second = benchmark.generate_scenarios(), benchmark.generate_scenarios()
        self.assertEqual(first, second)
        self.assertEqual(len(first), 6)
        self.assertEqual(first[0]["holdout_indices"], [2, 7, 12, 17, 22, 27, 32, 37])
        self.assertEqual(len(first[0]["train_indices"]), 35)
        noise = next(s for s in first if s["kind"] == "noisy")
        self.assertFalse(np.array_equal(noise["observed_qsca"], noise["latent_qsca"]))
        mismatch = next(s for s in first if s["kind"] == "mismatch")
        self.assertIsNone(mismatch["generation"]["constant_parameter_truth"])

    def test_public_manifest_excludes_truth_and_preserves_old_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            store = base / "store"
            store.mkdir()
            old = store / "old.json"
            old.write_text("unchanged", encoding="utf-8")
            result = benchmark.prepare(base / "out", base / "private", store, base / "agent")
            manifest = json.loads(Path(result["public_manifest"]).read_text(encoding="utf-8"))
            serialized = json.dumps(manifest)
            for forbidden in ("observed_qsca", "latent_qsca", "constant_parameter_truth", "183.47", "317.83"):
                self.assertNotIn(forbidden, serialized)
            self.assertEqual(len(manifest["cases"]), 4)
            self.assertEqual(old.read_text(encoding="utf-8"), "unchanged")
            self.assertEqual(len(list(store.glob("*.json"))), 5)
            for case in manifest["cases"]:
                self.assertIsNone(json.loads((store / f"{case['run_id']}.json").read_text())["final"])

    def test_private_paths_cannot_be_nested_in_agent_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "disjoint"):
                benchmark._check_separation(root / "agent" / "truth", root / "agent", root / "store")
            with self.assertRaisesRegex(ValueError, "outside"):
                benchmark._check_separation(root / "private", root / "agent", root / "agent" / "store")

    def test_scale_is_signal_relative_and_scoring_rejects_wrong_targets(self):
        self.assertAlmostEqual(benchmark.normalization_scale([3, 4]), np.sqrt(12.5))
        self.assertEqual(benchmark.normalization_scale([0, 0]), 1e-8)
        scenario = benchmark.generate_scenarios()[0]
        truth = scenario["generation"]["constant_parameter_truth"]
        with tempfile.TemporaryDirectory() as store:
            run = create_experiment(store, zip(scenario["wavelengths_nm"], scenario["observed_qsca"]))
            run_trial(store, run, *[truth[key] for key in benchmark.PARAMETERS])
            finalize(store, run)
            record = report_record(store, run)
            score = benchmark.score_record(record, scenario)
            self.assertLess(score["holdout_nrmse"], 1e-12)
            self.assertEqual(score["outcome"], "pass")
            record["target"][0][1] += .01
            with self.assertRaisesRegex(ValueError, "target differs"):
                benchmark.score_record(record, scenario)

    def test_evidence_needs_matching_scenario_and_explicit_complete_flag(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence_path = root / "evidence.json"
            record = {"run_id": "a" * 32, "scenario_id": "clean_a", "model": "test-model",
                      "session_id": "test-session", "complete": False, "evidence_path": "missing.json"}
            suite = {"agh_cases": [{"case_id": "clean_a", "run_id": "a" * 32}]}
            benchmark.write_json(evidence_path, [record])
            self.assertFalse(benchmark.load_agh_evidence(evidence_path, suite)["a" * 32]["complete"])
            record["complete"] = True
            benchmark.write_json(evidence_path, [record])
            with self.assertRaisesRegex(ValueError, "missing"):
                benchmark.load_agh_evidence(evidence_path, suite)
            record["complete"] = "false"
            benchmark.write_json(evidence_path, [record])
            with self.assertRaisesRegex(ValueError, "boolean"):
                benchmark.load_agh_evidence(evidence_path, suite)
            record["complete"] = False
            record["scenario_id"] = "clean_b"
            benchmark.write_json(evidence_path, [record])
            with self.assertRaisesRegex(ValueError, "wrong scenario"):
                benchmark.load_agh_evidence(evidence_path, suite)


if __name__ == "__main__":
    unittest.main()

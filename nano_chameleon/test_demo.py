"""Competition UI contract, colour assumptions and sealed holdout isolation."""
import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient
from colour_preview import transmission_colour
from demo_server import create_app


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(Path(self.tmp.name)), base_url="http://127.0.0.1:4190")
        token = self.client.get("/api/config").json()["token"]
        self.headers = {"Origin": "http://127.0.0.1:4190", "X-Demo-Token": token}

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def post(self, op, **data):
        return self.client.post("/api/" + op, json=data, headers=self.headers)

    def test_local_authorization(self):
        self.assertEqual(self.client.get("/api/config", headers={"Host": "evil.example"}).status_code, 403)
        self.assertEqual(self.client.post("/api/create", json={"case": "clean_a"}).status_code, 403)
        headers = {**self.headers, "Origin": "http://evil.example"}
        self.assertEqual(self.client.post("/api/create", json={}, headers=headers).status_code, 403)

    def test_preview_and_seal(self):
        state = self.post("create", case="clean_a").json()
        self.assertEqual(len(state["training"]), 35)
        self.assertNotIn("target", state)
        self.assertNotIn("final", state)
        self.assertEqual(state["holdout_count"], 8)
        args = dict(run_id=state["run_id"], diameter_nm=250, n_real=2, k=.03)
        preview = self.post("preview", **args).json()
        self.assertEqual(len(preview["curve"]), 35)
        self.assertEqual(self.post("trial", **args).json()["trial_count"], 1)
        state = self.post("validate", run_id=state["run_id"]).json()
        self.assertTrue(state["sealed"])
        self.assertEqual(len(state["final"]["holdout"]), 8)
        self.assertEqual(self.post("trial", **args).status_code, 400)
        self.assertEqual(self.post("preview", **args).status_code, 400)
        self.assertEqual(self.post("search", run_id=state["run_id"]).status_code, 409)

    def test_search_uses_training_and_logs(self):
        state = self.post("create", case="clean_b").json()
        state = self.post("search", run_id=state["run_id"]).json()
        self.assertGreater(state["trial_count"], 90)
        self.assertNotIn("final", state)
        self.assertEqual(len(state["trials"]), state["trial_count"])
        self.assertLessEqual(len(state["candidates"]), 3)

    def test_invalid_inputs_and_paths(self):
        for csv in [None, "x,y\n1,2", "wavelength_nm,qsca\n400,-1"]:
            self.assertEqual(self.post("create", csv=csv).status_code, 400)
        self.assertEqual(self.post("create", case="clean_a", n_env=True).status_code, 400)
        self.assertEqual(self.post("preview", run_id="../engine").status_code, 400)
        self.assertEqual(self.client.get("/assets/engine.py").status_code, 404)
        self.assertEqual(self.client.get("/api/evidence/unknown").status_code, 404)
        response = self.client.post("/api/create", content=b"x" * 120001, headers=self.headers)
        self.assertEqual(response.status_code, 413)

    def test_active_search_blocks_validation(self):
        state = self.post("create", case="clean_a").json()
        self.client.app.state.searching = True
        try:
            self.assertEqual(self.post("validate", run_id=state["run_id"]).status_code, 409)
            self.assertEqual(self.post("trial", run_id=state["run_id"], diameter_nm=250, n_real=2, k=.03).status_code, 409)
        finally:
            self.client.app.state.searching = False

    def test_archived_agh_and_failure_are_honest(self):
        for case in ["clean_a", "clean_b", "noisy", "mismatch"]:
            state = self.client.get("/api/evidence/" + case).json()
            self.assertTrue(state["sealed"])
            self.assertTrue(state["evidence"]["verified"])
            self.assertEqual(state["evidence"]["criterion_met"], case != "mismatch")
            self.assertEqual(state["source"], "agh")
        report = self.client.get("/evidence-report/mismatch")
        self.assertEqual(report.status_code, 200)
        self.assertIn("text/html", report.headers["content-type"])

    def test_colour_and_optical_depth(self):
        white = transmission_colour(250, 2, .03, optical_depth=0)
        self.assertTrue(all(v > .999 for v in white["srgb"]))
        self.assertAlmostEqual(white["relative_luminance"], 1, places=6)
        dark = transmission_colour(250, 2, .03, optical_depth=1)
        self.assertLess(dark["relative_luminance"], white["relative_luminance"])
        self.assertNotEqual(white["hex"], dark["hex"])
        self.assertTrue(all(0 <= v <= 1 for v in dark["srgb"]))
        self.assertIn("D65", dark["assumptions"])
        for depth in [-1, 3, float("nan"), True]:
            with self.assertRaises(ValueError):
                transmission_colour(250, 2, .03, optical_depth=depth)


if __name__ == "__main__":
    unittest.main()

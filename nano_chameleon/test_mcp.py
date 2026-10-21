"""Exercise the same stdio MCP transport that AGH will use."""

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from engine import create_experiment, spectrum


class McpTransportTests(unittest.TestCase):
    def test_tool_call_chain(self):
        with tempfile.TemporaryDirectory() as store:
            wavelengths = np.linspace(400, 760, 21)
            target = spectrum(wavelengths, 260, 2.35, 0.015)
            run_id = create_experiment(store, zip(wavelengths, target))
            asyncio.run(self._exercise(store, run_id))

    async def _exercise(self, store, run_id):
        env = os.environ.copy()
        env["NANO_CHAMELEON_STORE"] = store
        script = Path(__file__).with_name("mcp_server.py")
        params = StdioServerParameters(command=sys.executable, args=[str(script)], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                names = {tool.name for tool in (await client.list_tools()).tools}
                self.assertIn("simulate_candidate", names)
                self.assertIn("search_candidates", names)
                status = await client.call_tool("inspect_experiment", {"run_id": run_id})
                self.assertFalse(status.isError)
                trial = await client.call_tool("simulate_candidate", {
                    "run_id": run_id, "diameter_nm": 260.0, "n_real": 2.35, "k": 0.015,
                })
                self.assertFalse(trial.isError)
                search = await client.call_tool("search_candidates", {"run_id": run_id, "generations": 1})
                self.assertFalse(search.isError)
                validation = await client.call_tool("validate_unseen_wavelengths", {"run_id": run_id})
                self.assertFalse(validation.isError)
                after = await client.call_tool("simulate_candidate", {
                    "run_id": run_id, "diameter_nm": 261.0, "n_real": 2.35, "k": 0.015,
                })
                self.assertTrue(after.isError)


if __name__ == "__main__":
    unittest.main()

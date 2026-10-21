"""AGH-compatible MCP tools for a model-driven experiment loop."""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from engine import finalize, optimize, public_status, run_trial
from report import write_report
from engine import report_record


ROOT = Path(__file__).resolve().parent
STORE = Path(os.environ.get("NANO_CHAMELEON_STORE", ROOT / "runs"))
mcp = FastMCP("nano-chameleon")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
def inspect_experiment(run_id: str) -> dict:
    """Get training wavelengths, target Qsca, bounds, and best trial. Hidden targets stay sealed."""
    return public_status(STORE, run_id)


@mcp.tool()
def simulate_candidate(run_id: str, diameter_nm: float, n_real: float, k: float) -> dict:
    """Run one Mie simulation. Returns its training curve and RMSE; records every call."""
    return run_trial(STORE, run_id, diameter_nm, n_real, k)


@mcp.tool()
def search_candidates(run_id: str, generations: int = 20, seed: int = 7) -> dict:
    """Run a reproducible physics-guided search, recording every simulated curve. Returns the best training fit."""
    return optimize(STORE, run_id, generations, seed)


@mcp.tool()
def validate_unseen_wavelengths(run_id: str) -> dict:
    """Irreversibly lock the best trial and reveal scores at wavelengths unused for fitting."""
    return finalize(STORE, run_id)


@mcp.tool()
def export_experiment_report(run_id: str) -> dict:
    """After validation, write an interactive local report of all trials and the holdout."""
    return {"report_path": str(write_report(report_record(STORE, run_id), ROOT / "reports"))}


if __name__ == "__main__":
    mcp.run(transport="stdio")


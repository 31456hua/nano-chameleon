# Nano Chameleon

English | [简体中文](README.zh-CN.md)

<p align="center">
  <b>Target spectrum in, particle parameters out: a reproducible, auditable inverse-design pipeline for nano-chameleon colour.</b>
</p>

Team Fànshì (U226) · Members: Huà Yùsū (花豫苏), Hú Bīn (胡彬) · Hackathon 2026, undergraduate track

## Contents

- [Project overview](#project-overview)
- [Demo video](#demo-video)
- [Architecture](#architecture)
- [Integration standards](#integration-standards)
- [Quick start](#quick-start)
- [Historical results](#historical-results)
- [Repository layout](#repository-layout)
- [Model assumptions, scope and provenance](#model-assumptions-scope-and-provenance)
- [License](#license)

## Project overview

Nano Chameleon turns the **inverse design of nano-particle colour** into a runnable, checkable workflow. The team is given a target scattering spectrum; the goal is to recover the particle's optical parameters — diameter, refractive index *n* and extinction coefficient *k* — and to prove that the recovery generalizes to wavelengths it has never seen during fitting.

### Background

The colour of a nano-particle is a **structural colour**: Mie scattering of white light by a small sphere produces a wavelength-dependent scattering efficiency Q_sca(λ). Forward computation is easy (parameters → spectrum); inversion is hard, because

- **parameter coupling** — diameter and *n* compensate each other at the same resonance;
- **non-uniqueness** — different (d, n, k) can give nearly identical spectra, especially with noise;
- **model mismatch** — a wavelength-independent *n*/*k* cannot represent dispersive real materials at all.

Inversion is therefore a bounded search, not the solution of a unique equation. A result only counts after it survives a **sealed holdout test**: parameters are chosen on training wavelengths only, locked, and scored once on wavelengths that were hidden.

### Core features

- **Physics engine** — deterministic Mie scattering via [MiePython](https://github.com/scottprahl/MiePython), reproducible numerical optimization via SciPy differential evolution with local polishing.
- **Model-driven loop** — the Agnes agent plans and steers the experiment inside [Agnes Harness](https://github.com/AgnesAI-Labs/agnes-harness) (AGH): inspect the sealed target, propose candidates, call the physics tools through MCP, react to feedback, and export a report. Every candidate is recorded on disk; the agent never does the physics itself.
- **Sealed blind validation** — an internally held-out wavelength set is revealed exactly once after parameter locking; further fitting is refused.
- **Interactive demo station** — a local web front end with manual simulation, replay of the four archived Agnes runs, and one-click regeneration of reports.
- **Reproducible benchmark suite** — deterministic synthetic scenarios (clean, noisy, boundary, model-mismatch) with pre-declared thresholds and archived evidence.

### Innovation highlights

- **Division of labor, not "AI guesses physics."** Agnes is the *lab coordinator* — planning, feedback, records — while MiePython/SciPy own determinism. Physical correctness does not depend on model memory.
- **Blind holdout as the acceptance test.** Candidates are selected on training error only; disclosure is one-shot and irreversible (engine refuses trials after sealing).
- **Negative results are first-class evidence.** The model-mismatch scenario deliberately fails its 5% adequacy threshold (10.884% holdout NRMSE); the team reports it as evidence that the constant-(*n*,*k*) model is out of scope rather than hiding it.
- **Full auditability.** 1,920 archived candidate curves, native AGH trajectories, checksums and dependency pins let anyone reproduce every number in this repository.

Scope statement: results come from homogeneous spheres with constant *n*/*k* on synthetic data, for simulation screening and scientific-computing demonstration; there are no real-material experiments and no guarantee of parameter uniqueness.

## Demo video

**[Watch the 4-minute AGH demo on Bilibili](https://www.bilibili.com/video/BV1EXpQ6MEMP/)** — target setup, the Agnes loop, the sealed holdout reveal and the exported report.

The source file of this recording (U226_范式_纳米变色龙_演示_AGH版.mp4, uploaded 2026-10-12) is not redistributed from the repository; the Bilibili link is the canonical reference.

## Architecture

Four cooperating layers; each keeps a different responsibility and its own audit surface.

```
 Agnes model (agnes-3.0-flash, via AGH provider)
   plans · proposes candidates · reacts to feedback · records decisions
                │  MCP (JSON-RPC over stdio)
 Agnes Harness (AGH) — execution foundation
   sessions · tool approval · native trajectory · recovery
                │  5 nano-chameleon tools
 nano-chameleon service (Python, stdio MCP server)
   sealed experiment store · holdout sealing · trial recording
                │  calls
 Deterministic physics & numerics (MiePython + SciPy + NumPy)
   forward Mie Qsca(λ) · differential evolution + polish · RMSE
```

### Core modules

| Module | Responsibility |
| --- | --- |
| `nano_chameleon/engine.py` | Target CSV validation, experiment store (JSON per `run_id`), holdout sealing, trial recording, optimizer, one-shot finalize |
| `nano_chameleon/mcp_server.py` | stdio MCP service exposing the 5 tools below (FastMCP) |
| `nano_chameleon/demo_server.py` | Local web demo station: manual simulation, archived-run replay, interactive report |
| `nano_chameleon/benchmark.py` | Deterministic synthetic scenarios, SciPy baseline runs, HTML/JSON summary reports |
| `nano_chameleon/report.py` | Self-contained interactive HTML report of all trials and the holdout |
| `nano_chameleon/cli.py` | Command-line workflow (`prepare / demo / fit / trial / status / validate / report`) |
| `AGH_trace/`, `evidence/`, `offline_validation/` | Archived native trajectories, test logs and sealed validation sets (with SHA-256 in `SHA256SUMS.txt`) |

### Execution flow

1. `prepare` loads the target CSV, seals the internal holdout set, and stores it under `runs/` — the agent only ever sees training points through the tools.
2. The Agnes task loop: `inspect_experiment` → manual `simulate_candidate` trials → `search_candidates` (physics-guided, reproducible) → feedback-driven trials.
3. `validate_unseen_wavelengths` locks the best trial by training error, reveals holdout scores, and seals the experiment.
4. `export_experiment_report` writes an interactive local report.

The benchmark layer generates six deterministic synthetic scenarios (two clean targets, a noisy target, a dispersive target that violates the constant-(*n*,*k*) model, plus two parameter-bound probes) and runs sealed, reproducible baselines; archived results are summarized in HTML with no network access.

## Integration standards

### MCP tool interface

Transport: **JSON-RPC 2.0 over stdio**; server name `nano-chameleon` (FastMCP). Tool catalog, parameter types and postconditions:

| Tool | Parameters | Postcondition |
| --- | --- | --- |
| `inspect_experiment(run_id)` | `run_id: str` (32-hex) | read-only; returns model, *n_env*, bounds, training pairs, holdout count, best trial; sealed targets stay hidden |
| `simulate_candidate(run_id, diameter_nm, n_real, k)` | floats within [50, 500] nm, [1.05, 2.8], [0, 0.35] | one recorded Mie trial; returns training curve + RMSE; rejected once sealed |
| `search_candidates(run_id, generations=20, seed=7)` | `generations ∈ [1, 30]` (int), `seed: int` | reproducible differential evolution with local polishing; returns best training fit |
| `validate_unseen_wavelengths(run_id)` | — | irreversible: locks best trial, reveals holdout RMSE/NRMSE, seals the experiment |
| `export_experiment_report(run_id)` | — | requires a finished validation; returns the HTML report path |

Protocol invariants:

- **Sealed holdout** — holdout targets are revealed once, at finalize; all further trial writes are refused.
- **Recording** — every candidate (parameters, full curve, RMSE) is persisted; nothing is recomputed or fabricated later.
- **Errors** — invalid input, out-of-bounds parameters, non-finite values, duplicate wavelengths or post-seal writes raise `ValueError`/protocol errors, never silent failures.
- **Isolation** — one service process writes one experiment; batch tasks run serially.

### AGH integration

Run the MCP server from the project's own virtual environment; point AGH's MCP configuration at the interpreter plus script path:

```sh
# from the Agnes Harness source root (see its official docs for current syntax)
node packages/cli/dist/local/agnes.mjs mcp add nano-chameleon \
  --name nano-chameleon \
  --stdio "<path-to-python>" \
  --arg "<abs-path-to>/nano_chameleon/mcp_server.py"
```

Then review, trust, enable and check the tool catalog in AGH, and start a task from `nano_chameleon/AGH_TASK.md` (replace the `run_id`). Approval mode, provider keys and model selection stay in AGH; this repository stores none. The scheduler in `agh_dispatch.py` is a bounded, serial extension: one search ≤ 15 generations, ≤ 12 manual trials, single validation, at most two report exports per task.

### Demo station HTTP API

Local-only loopback service (binds `127.0.0.1`/`localhost` only; POSTs require the per-launch demo token issued by `/api/config`). Operations:

| Route | Method | Purpose |
| --- | --- | --- |
| `/` | GET | demo UI |
| `/api/config` | GET | per-launch token and preset case list |
| `/api/evidence/{case}` | GET | replay one archived AGH run with verified-trajectory audit |
| `/api/create` | POST | create a sealed experiment from a target CSV or preset case |
| `/api/preview` | POST | compute the training curve and transmission colour preview for candidate parameters |
| `/api/trial` | POST | run one recorded physics trial |
| `/api/search` | POST | run the bounded reproducible optimizer (5 generations, seed 7) |
| `/api/validate` | POST | finalize: lock parameters and reveal holdout |
| `/api/report` | POST | export the interactive HTML report |
| `/api/colour` | POST | compute the transmission colour for given parameters |
| `/report/{run_id}`, `/evidence-report/{case}` | GET | fetch generated report HTML |

### Data formats

- **Target CSV** — `wavelength_nm,qsca` (UTF-8, BOM tolerated); 15–400 rows; wavelengths strictly positive, unique, ascending; Qsca finite, non-negative.
- **Experiment JSON** — per `run_id` under `runs/`; the sealed store is off-limits to the agent by design; `NANO_CHAMELEON_STORE` can relocate it.
- **Report HTML** — self-contained (inline JS/CSS), offline; interactive charts for every trial and the holdout.

## Quick start

Python 3.11+. Commands run from the repository root; the first install needs network access.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r nano_chameleon\requirements-verified.txt
.\.venv\Scripts\python.exe nano_chameleon\demo_server.py --port 4190
```

macOS / Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r nano_chameleon/requirements-verified.txt
.venv/bin/python nano_chameleon/demo_server.py --port 4190
```

Open <http://127.0.0.1:4190/>. If the port is busy, change the port in the command and the address to `4191`.

- **Manual simulation** — runs the real physics and numerical search.
- **Replay archived Agnes runs** — plays back the four historical tasks.
- **Run a new Agnes loop** — install AGH separately and configure your own provider and the MCP service; see [reproducibility notes](docs/REPRODUCE.md).

The web service is local-only. `127.0.0.1` is *your own* machine; after publishing the source, others download it and start it on their own machines.

### Tests

Windows:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s nano_chameleon -p "test_*.py" -v
```

macOS / Linux:

```bash
.venv/bin/python -m unittest discover -s nano_chameleon -p 'test_*.py' -v
```

The public copy carries the archived 42-test log of 2026-10-11/12; this round's re-verification on the public copy is in [evidence](evidence/). The relationship between the sealed records, the original tests and the re-checks is described in [docs/ARCHIVE.md](docs/ARCHIVE.md).

## Historical results

Four archived Agnes tasks, 1,920 recorded candidate curves in total, model `agnes-3.0-flash`, verified against native AGH trajectories:

| Synthetic target | Candidates | Holdout NRMSE | Pre-declared threshold | Outcome |
| --- | ---: | ---: | ---: | --- |
| Clean A | 647 | 0.0000293% | 1% | passed |
| Clean B | 643 | 0.00000118% | 1% | passed |
| Noisy | 351 | 2.174% | 6% | passed |
| Dispersive mismatch | 279 | 10.884% | 5% | **not met** — reported as a model-adequacy boundary |

In addition, 18 seeded SciPy numerical baselines (7,576 evaluations) are archived as a separate evidence class and **do not count as Agnes calls**. All targets are synthetic; holdout validation measures in-band interpolation only. A good fit does not prove parameter uniqueness, and the failed mismatch result is kept on purpose. Details: [BENCHMARK.md](nano_chameleon/BENCHMARK.md), [AGH_SCHEDULE.md](nano_chameleon/AGH_SCHEDULE.md), [VERIFICATION.md](nano_chameleon/VERIFICATION.md).

## Repository layout

| Path | Contents |
| --- | --- |
| `nano_chameleon/` | engine, MCP server, demo station, CLI, tests, archived runs and reports |
| `AGH_trace/` | the four archived native execution traces |
| `offline_validation/` | the sealed synthetic validation sets |
| `docs/` | project, reproducibility, sources and archive notes |
| `evidence/` | historical verification logs plus this public copy's re-check logs |
| `LICENSES/` | third-party license texts collected for the project |
| `SHA256SUMS.txt` | integrity checks for archived files |

## Model assumptions, scope and provenance

- Model: homogeneous, mono-disperse sphere; *n*/*k* constant across the band (absorption convention n − i·k); medium index 1.0. No material identification, arbitrary shapes, shells, size distributions or real fabrication recipes.
- Data: program-generated synthetic spectra; no third-party measured spectra.
- AI assistance: code, tests, UI, docs and experiment scheduling used AI assistance; the archived agent tasks ran on a model identified as `agnes-3.0-flash` calling the numerical tools through AGH. No new Agnes/CNN weights were trained; the 18 SciPy baselines are not Agnes calls.
- Full component and asset provenance: [docs/SOURCES.md](docs/SOURCES.md).

## License

Team-authored software and its documentation: [MIT](LICENSE). Third-party components keep their own licenses — see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [LICENSES](LICENSES/). The externally hosted demo video and its audio are not redistributed from this repository and are not re-licensed under the project's MIT license.

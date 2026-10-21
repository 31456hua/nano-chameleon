# Nano Chameleon Benchmark

The benchmark separates a reproducible SciPy physics optimizer from actual AGH
model sessions. It generates six deterministic synthetic scenarios and creates
four fresh, sealed MCP experiments for AGH: two distinct clean targets, a noisy
target, and a dispersive target that violates the constant-index fitting model.
Two additional numerical scenarios probe the lower and upper parameter bounds.

## Commands

Run from this directory using the same Python environment as `engine.py`.
The report additionally requires `matplotlib` (tested with 3.11.2).

```text
python benchmark.py prepare
python benchmark.py baseline SUITE_ID --generations 15 --seeds 7 19 43
python benchmark.py summarize SUITE_ID
python benchmark.py summarize SUITE_ID --agh-evidence PATH_TO_EVIDENCE_SUMMARY_JSON
python -m unittest test_benchmark -v
```

`prepare` prints the suite ID, public task manifest, agent workspace and AGH
experiment IDs. It does not run AGH or access any Provider configuration.
`baseline` creates new experiments in the suite's separate `baseline_runs/`
directory. Every previous experiment is retained; repeated baseline invocations
append a new batch rather than overwrite results. The default batch is 18 runs,
six scenarios times three seeds. Generations are bounded to 10-20 and seeds to
one-three. SciPy polishing is enabled and adds candidate evaluations beyond the
15-generation differential evolution stage.

`summarize` writes a self-contained scientific HTML report and machine-readable
summary within the suite directory. The latest report is also exposed as
`benchmark_report.html`; earlier suite reports and all experiment records remain
in `benchmarks/SUITE_ID/`. Matplotlib figures are embedded, and compact charts are
rendered separately for narrow screens. The report requires no network access.

## Data And Blind Evaluation

All scenarios contain the same 43 wavelengths from 390 to 810 nm. Sorted indices
2, 7, 12, 17, 22, 27, 32 and 37 are held out. Baselines and designated AGH
experiments use identical observed targets and splits. Only the training samples
are exposed through MCP before final validation.

Private generation parameters and complete synthetic arrays stay under
`work/benchmark_private/SUITE_ID/`. The shared MCP store also contains the complete
sealed targets and stays outside the AGH workspace. The clean AGH workspace
contains only a public task manifest, which excludes ground truth and raw
spectral arrays. This is workflow isolation, not an operating-system sandbox;
the AGH controller must enforce the MCP-only task policy.

The benchmark summary and report are final evaluation artifacts and must remain
outside an active AGH workspace. The JSON summary contains recovered parameters
and post-validation diagnostics. The source code contains the deterministic
generator, so source access is also prohibited for active benchmark tasks.

## Scoring

NRMSE is RMSE divided by the RMS of observed training Qsca, with a denominator
floor of 1e-8. The same training-only scale is used for training and held-out
errors. This prevents a weak signal near the lower parameter bounds from gaining
an artificially favorable score through small absolute values.

The criteria are declared before fitting: 1% held-out NRMSE for clean and boundary
spectrum recovery; 6% for noisy observations generated with a 2% signal-relative
Gaussian sigma. The dispersive case has a 5% approximation-adequacy threshold,
with no constant n,k ground truth. An inadequate mismatch fit is evidence of
limited model adequacy on this grid, not automatic evidence of optimizer failure.
Parameter errors are diagnostic; a good finite-spectrum fit does not establish
unique recovery. All seed outcomes are reported, including misses. Figures select
a representative seed by training error only, never held-out score.

## AGH Evidence

Use a top-level JSON list containing one item per attempted designated experiment:

```json
[
  {
    "scenario_id": "clean_a",
    "run_id": "EXPERIMENT_ID_FROM_PUBLIC_MANIFEST",
    "model": "ACTUAL_MODEL_FROM_NATIVE_TRACE",
    "session_id": "ACTUAL_NATIVE_SESSION_ID",
    "evidence_path": "clean_a.agh.json",
    "complete": false
  }
]
```

Paths may be absolute or relative to the evidence manifest. The controller may
set `complete` to true only after verifying the native model/session record,
required tool order and counts, validation, and exported report. The report
checks that the manifest references the correct prepared scenario and experiment,
the evidence file exists, and the experiment is sealed. It independently audits
the selective native trajectory: Agnes model headers, increasing event order,
matched tool calls/results, parameter bounds, budgets, initial feedback before
search, post-search feedback before validation, and export after validation.
Read-only MCP catalog listing is permitted, not configuration changes. A numerical
fit alone cannot establish protocol completion. Partial or unverified attempts remain separate. Agent protocol
completion and physical fit/adequacy criteria are distinct outcomes.

## Current Baseline

Suite `20261010T151242Z_161152a2` completed all 18 baseline runs with 7,576 recorded
candidate evaluations. Both clean targets, the lower-bound case, and the noisy
case met their criteria for all three seeds. The upper-bound case met its 1%
criterion for one of three seeds; the other two stopped near 4.98% held-out NRMSE.
The dispersive case produced 10.88-11.02% held-out NRMSE across seeds and did not
meet the 5% model-adequacy threshold. These are synthetic interpolation results,
not evidence of real-material accuracy or statistical significance.

## Completed AGH Batch

On 2026-10-11 all four designated runs completed native protocol verification
using `agnes-3.0-flash`, with 1,920 recorded candidate evaluations. Clean A/B and
the noisy case passed the predeclared criteria; the mismatch case produced
10.884% held-out NRMSE and failed the 5% model-adequacy criterion. Clean A needed
a report-only recovery in the original session after an end-of-turn error.
Its failed snapshot is retained and no further numerical trial or validation
occurred after disclosure. See `AGH_SCHEDULE.md` for IDs, links and commands.

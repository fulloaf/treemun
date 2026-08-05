# Treemün 2.0.0 definitive update

This update combines the mandatory pre-thinning initialization and rotation-reset logic with the final optimization improvements.

## Final optimization changes

- `solve_model()` accepts `threads` and `time_limit_seconds`.
- Runtime controls are translated to Pyomo configuration fields when available and otherwise to native CPLEX, HiGHS, CBC, Gurobi, or GLPK options.
- Extracted solutions record requested runtime controls and configured native options in `solve_history`.
- The three-objective epsilon front reuses:
  - the global economic anchor when it satisfies the requested epsilon bounds;
  - the lexicographic minimum-green-up anchor for the exact minimum-conflict bound;
  - previously solved looser epsilon optima when they remain feasible and therefore optimal for stricter bounds.
- Each front row reports `solution_source` and zero front-specific timing for reused points.
- DataFrame attributes report requested combinations, actual new solves, reused solutions, avoided solver calls, infeasible combinations, and aggregate model-build and solver time.

## Notebook defaults

- All 105 bundled stands are retained.
- The three-objective grid requests 3 carbon levels by 2 green-up levels.
- The actual number of new spatial MILP solves can be lower than six because of reuse.
- Solver threads are capped at 8 and reduced automatically when common scheduler CPU-allocation variables report fewer CPUs.
- `SOLVER_TIME_LIMIT_SECONDS` is `None` by default and can be changed by the user.

## Validation

- 41 tests passed from the cleaned repository source tree.
- The same 41 tests passed from the unpacked source distribution.
- 1 Pyomo-dependent test module was skipped because Pyomo was unavailable in the validation environment.
- The wheel was imported successfully from an isolated target directory.
- `treemun_sim.__version__` reported `2.0.0`, and the bundled lookup table loaded all 34 equations.
- All three retained notebooks passed notebook-format validation.
- The original `.xlsm` file passed basic OOXML container-integrity checks.

## Definitive release-source contents

- Generated `outputs`, `outputs_*`, and `demo_outputs` directories are excluded.
- Caches, Jupyter checkpoints, bytecode, `dist`, `build`, and `*.egg-info` artifacts are excluded.
- Only the two authoritative Mg-harmonized benchmark notebooks are retained in `benchmark_notebooks_and_generator/`.
- `DatosArmonizados_Plantaciones_VFinal.xlsm` and `DatosArmonizados_Plantaciones_VFinal.csv` are retained as the original source tables used to derive and validate the surrogate functions.
- `MANIFEST.in` makes the source distribution self-contained for tests, examples, documentation, benchmark notebooks, and provenance data.

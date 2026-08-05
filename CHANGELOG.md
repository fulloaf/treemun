# Changelog

## 2.0.0
- Made pre-thinning initialization mandatory for `Pinus radiata`; initial post-thinning equations are rejected.
- Required every initial Pinus equation to define a valid `next_equation_id` leading to a post-thinning Pinus equation.
- Changed overdue-thinning policies (`initial_age > thinning_age`) to fully harvest the initial rotation in period 1 and restart period 2 at age 1 on the pre-thinning curve.
- Added `final_harvest_reason` and `initial_rotation_reset_triggered` trajectory diagnostics.
- Restored policy-invariant initial dry-wood stock, enabling native proportional terminal-stock constraints.
- Updated the bundled example from 768 to 780 feasible stand-policy alternatives under the new reset rule.
- Added three explicit economic modes: `gross_revenue`, `net_unit_value`, and `detailed_cash_flow`.
- Added transparent revenue and cost accounting by stand, policy, period, and operation.
- Added configurable variable, transport, operation, management, and replanting costs.
- Added a full 105-stand Jupyter notebook covering all economic modes, thinning diagnostics, carbon, weighted and epsilon fronts, even flow, adjacency, three-objective optimization, 3D visualization, and GeoPackage export.
- Added the fixed-fraction thinning fallback with continuous post-thinning increments and explicit diagnostic columns.
- Reclassified terminal `pulpwood` Pinus equations as `unthinned`; only equations with an explicit post-thinning continuation are labelled `pre_thinning_1250_700`.

### Release packaging

- Added `MANIFEST.in` so source distributions include tests, documentation, examples, benchmark notebooks, and the original harmonized source tables.
- Removed generated outputs, caches, checkpoints, build artifacts, and superseded benchmark notebooks from the release source tree.
- Retained only the two authoritative Mg-harmonized benchmark notebooks and their original `.xlsm`/`.csv` source tables.

### Solver installation metadata

- Added `highspy` to the `optimization` and `complete` extras.
- Added an optional `cplex` extra without forcing commercial software into the default installation.
- Added `environment.yml` for CBC + HiGHS and `environment-cplex.yml` for the optional IBM CPLEX runtime.
- Added `requirements-cplex.txt` and documented solver-neutral installation.


### Corrected

- Reinterpreted all growth-equation outputs as metric tonnes of dry wood per hectare rather than cubic metres.
- Added explicit pre-operation, harvested, and post-operation dry-wood variables.
- Corrected ending stock so a final harvest in the final period leaves zero dry wood.
- Removed wood-density conversion from carbon accounting.

### Changed

- Standardized the public API, source identifiers, parameters, columns, outputs, documentation, and lookup table in English.
- Renamed the initial Pinus curve from `post_thinning_1250_700` to `pre_thinning_1250_700`.
- Renamed `post_pruning_thinning_700_300` to `post_thinning_700_300`.
- Removed pruning from operation terminology; the simulator now reports only `none`, `thinning`, and `final_harvest`.
- Replaced ambiguous `stand_condition` with `growth_curve`.
- Corrected `Eucapyltus` to `Eucalyptus globulus`.
- Introduced symmetric even-flow formulations.
- Added assignment-bound scaling for direct weighted models and payoff-range ideal–nadir normalization for weighted Pareto fronts.
- Adopted GeoPackage as the preferred spatial output.
- Replaced legacy packaging files with `pyproject.toml`.

### Added

- Standing-wood carbon stock-time objective in tC·year.
- Migration helpers for 1.x stand files and early 2.0 growth-curve labels.
- Automated tests for lookup terminology, dry-wood accounting, carbon, migration, and spatial adjacency.
- Added exact spatial-conflict expressions, three-objective payoff tables, and NPV–carbon–adjacency epsilon fronts.
- Added a full-capability Jupyter notebook with two- and three-objective visualizations.
- Restored `requirements.txt` and `requirements-dev.txt` as convenience environment files while retaining `pyproject.toml` as the dependency source of truth.

### Removed

- Legacy notebooks and documentation figures with obsolete units.
- Duplicate optimization utilities and unused source modules.
- Legacy `setup.py`; project metadata is maintained in `pyproject.toml`.

### Terminal conditions, timing, and 3D interpretation

- Added `terminal_value_per_dry_t` to detailed cash-flow accounting, including transparent nominal and discounted terminal-value columns.
- Added `minimum_ending_dry_wood_fraction` as a landscape-level terminal stock safeguard relative to initial dry wood.
- Added model-build, solver, and total elapsed-time fields to extracted solutions and Pareto tables.
- Renamed user-facing spatial outputs to `greenup_event_conflict_count`; previous spatial-conflict names remain compatibility aliases.
- Reused the bi-objective anchors in the three-objective payoff table, reducing repeated spatial MILP solves.
- Reused payoff anchors and previously solved looser epsilon optima inside the three-objective epsilon grid whenever optimality is preserved, with explicit `solution_source` and avoided-solver-call diagnostics.
- Added cross-solver `threads` and `time_limit_seconds` controls for CPLEX, HiGHS, CBC, and supported Gurobi interfaces, including runtime-option history in extracted solutions.
- Reduced the demonstration three-objective grid to 3 carbon levels by 2 green-up levels while retaining all 105 stands.
- Added hyperplane-based knee-point identification and a large interactive triangulated 3D Pareto visualization.
- Corrected carbon summaries so incompatible candidate policies are not summed as if they formed one landscape plan.
- Expanded thinning diagnostics with quantiles, histograms, and management-regime summaries.

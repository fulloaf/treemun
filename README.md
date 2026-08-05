# Treemün 2.0.0

Treemün simulates management trajectories for *Pinus radiata* and *Eucalyptus globulus*, prepares mixed-integer harvest-scheduling models, calculates standing-wood carbon, and supports spatial adjacency and green-up constraints.

## Physical units

The growth equations project **metric tonnes of dry wood per hectare**, not cubic metres. At stand level, the principal variables are:

- `standing_dry_wood_t_before_operation`
- `harvested_dry_wood_t`
- `standing_dry_wood_t_after_operation`
- `ending_dry_wood_t`

Economic input values are consequently expressed as currency per tonne of dry wood.

## Growth-curve terminology

The lookup table describes the role of each curve relative to thinning:

- `unthinned`: eucalyptus or other trajectories without a separate thinning transition;
- `pre_thinning_1250_700`: the curve used before thinning from 1,250 to 700 trees per hectare;
- `post_thinning_700_300`: the curve used after that thinning transition and before the later density state represented by the source equation.

Pruning is not represented as a separate Treemün operation. Simulation outputs use only `none`, `thinning`, and `final_harvest`.

Early labels `post_thinning_1250_700` and `post_pruning_thinning_700_300` are accepted only by the migration layer and are converted to the canonical names with a deprecation warning.

## Installation

### Basic installation from PyPI

```bash
python -m pip install treemun-sim
```

### Complete installation from PyPI with HiGHS

```bash
python -m pip install "treemun-sim[complete]"
```

The `complete` extra installs Pyomo, the `highspy` Python interface to HiGHS,
and the spatial dependencies. It does not attempt to install CBC or a commercial
CPLEX license.

From a cloned source repository, the equivalent convenience command is:

```bash
python -m pip install -r requirements.txt
```

### Conda environment with CBC and HiGHS

CBC is distributed as a native executable rather than a normal Treemün Python
dependency. The recommended reproducible installation is:

```bash
conda env create -f environment.yml
conda activate treemun200
```

This environment installs `coincbc`, `highspy`, and Treemün in editable mode with
tests and notebook dependencies.

To update an existing environment instead:

```bash
conda install -c conda-forge coincbc highspy -y
python -m pip install --upgrade -e ".[complete,test,notebook]"
```

### Optional CPLEX support

If a licensed CPLEX executable is already available in `PATH`, Treemün can use it
without installing another Python package:

```python
results = tm.solve_model(model, solver_name="cplex")
```

To create a separate environment containing CBC, HiGHS, and the IBM CPLEX Python
API / Community Edition runtime:

```bash
conda env create -f environment-cplex.yml
conda activate treemun200-cplex
```

Alternatively, install the optional CPLEX extra with pip:

```bash
python -m pip install -r requirements-cplex.txt
```

The CPLEX runtime installed from pip or Conda may be subject to IBM Community
Edition limits unless it is connected to an appropriate full license.

### Development environment

From a cloned source repository:

```bash
python -m pip install --upgrade -e ".[complete,test,notebook]"
```

The equivalent convenience command is:

```bash
python -m pip install -r requirements-dev.txt
```

The officially supported solver identifiers are:

```text
cbc
highs
appsi_highs
cplex
cplex_direct
cplex_persistent
appsi_cplex
```

Availability depends on the solver executable, Python API, and license installed
in the active environment.

### Solver threads and time limits

Treemün translates common runtime controls to the native options of CPLEX,
HiGHS, CBC, and supported Gurobi interfaces:

```python
results = tm.solve_model(
    model,
    solver_name="cplex",
    relative_gap=0.01,
    threads=8,
    time_limit_seconds=None,
)
```

`threads=None` leaves the solver default unchanged. A positive integer caps the
number of solver threads; it does not request additional CPUs from a cluster
scheduler. The job allocation must provide at least that many CPUs. Extracted
solutions record the requested gap, thread count, time limit, and native solver
options in `solve_history`.

## Input stand table

The canonical schema is:

```text
stand_id
area_ha
species
initial_age
zone
site_index
management_regime
growth_curve
initial_density_trees_ha
```

See `examples/forest_stands.csv`. Treemün 1.x columns and categorical labels can be converted through `convert_v1_stand_file()`.

## Lookup table

`treemun_sim/data/lookup_table.csv` uses the following fields:

```text
equation_id
next_equation_id
species
zone
initial_density_trees_ha
site_index
management_regime
growth_curve
alpha
beta
gamma
```

`next_equation_id` connects a pre-thinning equation to its post-thinning equation.

### Mandatory Pinus initial state

Every `Pinus radiata` input stand must reference a pre-thinning equation with a valid `next_equation_id` leading to a post-thinning Pinus equation. A post-thinning equation is an internal state reached only after a thinning operation simulated inside the planning horizon; it is not accepted as an initial stand condition.

If a selected policy has `thinning_age < initial_age`, Treemün does not assume that an undocumented thinning occurred before the plan. Instead, it fully harvests the observed pre-thinning stock in period 1, records `final_harvest_reason = "overdue_thinning_rotation_reset"`, and starts period 2 at biological age 1 on the original pre-thinning equation. This guarantees a policy-invariant initial stock for every stand.

## Simulation

```python
import treemun_sim as tm

forest, policy_summary, ending_stock, harvest, carbon_stock_time = (
    tm.simulate_forest(
        stands_file="examples/forest_stands.csv",
        horizon=30,
        include_carbon=True,
        return_carbon_for_optimization=True,
    )
)
```

Each trajectory contains dry-wood stock before the operation, harvested dry wood, and the stock remaining after the operation. A final harvest always leaves zero post-operation stock in that period. The diagnostic columns `final_harvest_reason` and `initial_rotation_reset_triggered` distinguish scheduled harvests from period-1 resets caused by an overdue thinning age.

For thinning, Treemün first evaluates the linked pre- and post-thinning curves at the intervention age. If the post-thinning curve would retain no more than 10% of the pre-thinning stock, the default 30% fixed-fraction fallback is applied. The corrected residual stock is then carried forward using the increments of the post-thinning curve. Both thresholds are configurable and the selected method is recorded in the trajectory outputs.

## Carbon objective

Carbon is calculated directly from dry-wood mass:

\[
C_t=f_C\,DW_t.
\]

No wood-density conversion is applied. The initial optimization metric is cumulative post-operation standing-wood carbon stock-time:

\[
Z_C=\sum_t C^{\mathrm{post}}_t\Delta_t,
\]

expressed in `tC·year` for annual periods. This first implementation covers standing wood only and does not include roots, foliage, soil, dead wood, harvested-wood products, substitution effects, decay, or operational emissions.

## Economic accounting and optimization

Treemün supports three explicit economic interpretations:

- `gross_revenue`: discounted harvested dry wood multiplied by income per tonne;
- `net_unit_value`: discounted harvested dry wood multiplied by a user-supplied net margin per tonne;
- `detailed_cash_flow`: revenue minus variable, transport, operation, management, and replanting costs, producing a true net present value.

```python
GROSS_REVENUE_PARAMETERS = {
    "revenue_per_dry_t": {
        tm.PINUS: 85.0,
        tm.EUCALYPTUS: 92.0,
    }
}

NET_UNIT_VALUE_PARAMETERS = {
    "net_value_per_dry_t": {
        tm.PINUS: 55.0,
        tm.EUCALYPTUS: 61.0,
    }
}

DETAILED_CASH_FLOW_PARAMETERS = {
    "revenue_per_dry_t": {tm.PINUS: 85.0, tm.EUCALYPTUS: 92.0},
    "variable_cost_per_dry_t": {tm.PINUS: 10.0, tm.EUCALYPTUS: 9.0},
    "transport_cost_per_dry_t": 6.0,
    "thinning_cost_per_dry_t": 8.0,
    "final_harvest_cost_per_dry_t": 12.0,
    "thinning_cost_per_ha": 120.0,
    "final_harvest_cost_per_ha": 180.0,
    "replanting_cost_per_ha": {tm.PINUS: 1_200.0, tm.EUCALYPTUS: 1_000.0},
    "annual_management_cost_per_ha": 15.0,
    "replanting_delay_periods": 0,
}
```

The transparent accounting helper can be used before optimization:

```python
evaluation = tm.evaluate_forest_economics(
    forest,
    economic_mode="detailed_cash_flow",
    discount_rate=0.08,
    economic_parameters=DETAILED_CASH_FLOW_PARAMETERS,
)

display(evaluation.summary_by_policy)
display(evaluation.cash_flow_table)
```

A detailed NPV–carbon model is built as follows:

```python
model = tm.build_forest_management_model(
    policy_summary=policy_summary,
    ending_dry_wood_by_policy=ending_stock,
    harvested_dry_wood_by_period=harvest,
    carbon_stock_time_by_period=carbon_stock_time,
    forest=forest,
    horizon=30,
    economic_mode="detailed_cash_flow",
    economic_parameters=DETAILED_CASH_FLOW_PARAMETERS,
    discount_rate=0.08,
    minimum_ending_dry_wood_t=25_000,
    objective="weighted",
    npv_weight=0.5,
    carbon_weight=0.5,
    even_flow_mode="two_sided_average",
    even_flow_tolerance=0.10,
)

results = tm.solve_model(model, "cbc")
solution = tm.extract_solution(model, results)
print(solution["economic_metric"], solution["economic_value"])
```

`solution["npv_value"]` remains as a compatibility alias. It is a true NPV only in `detailed_cash_flow` mode; new code should use `economic_metric` and `economic_value`.

### Multiobjective scaling

Direct weighted models use analytical stand-assignment bounds to create dimensionless economic and carbon terms. For Pareto analysis, `build_weighted_pareto_front()` uses payoff-range ideal–nadir normalization by default, based on the economic and carbon anchor solutions. Epsilon-constraint models retain natural units because the economic metric, carbon, and spatial-conflict bounds are interpreted directly.

```python
payoff = tm.build_biobjective_payoff_table(
    solver_name="appsi_highs",
    model_options=model_options,
)

weighted_front = tm.build_weighted_pareto_front(
    weights=[0.0, 0.25, 0.5, 0.75, 1.0],
    solver_name="appsi_highs",
    model_options=model_options,
    payoff_table=payoff,
)

epsilon_front = tm.build_epsilon_constraint_front(
    epsilon_objective="carbon",
    number_of_points=11,
    solver_name="appsi_highs",
    model_options=model_options,
)
```

## Spatial workflow

GeoPackage is the preferred format because Shapefile truncates descriptive field names.

```python
edges = tm.build_adjacency_edges(
    "examples/treemun_landscape.gpkg"
)

final_harvest = tm.build_final_harvest_indicator(forest)

tm.add_greenup_adjacency(
    model,
    adjacency_edges=edges,
    final_harvest_indicator=final_harvest,
    greenup_window=2,
    mode="hard",
)
```

Complete spatial and three-objective examples are described in `README_SPATIAL.md`. The executable demonstration notebook is `examples/Treemun_2_0_0_full_105_stands_analysis.ipynb`.

## Reproducible benchmarks and source-table provenance

The release retains two authoritative Mg-harmonized benchmark notebooks in `benchmark_notebooks_and_generator/`:

- `Treemun_2_0_0_surrogate_vs_source_tables_benchmark_Mg_harmonized.ipynb`;
- `Treemun_2_0_0_biobjective_solver_benchmark_105_stands_Mg_harmonized.ipynb`.

The original harmonized plantation tables used to generate and validate the surrogate functions are preserved in the same directory as `DatosArmonizados_Plantaciones_VFinal.xlsm` and `DatosArmonizados_Plantaciones_VFinal.csv`. Generated benchmark outputs are intentionally excluded from the release and can be recreated by executing the notebooks.

## Migration

The intentional API and unit changes from 1.x are documented in `MIGRATION_1_TO_2.md`.

## Terminal stock and residual value

Treemün can reduce end-of-horizon bias in two complementary ways.

A minimum ending stock can be imposed as an absolute quantity or as a fraction
of the initial landscape stock:

```python
model = tm.build_forest_management_model(
    ...,
    minimum_ending_dry_wood_t=50_000,
    minimum_ending_dry_wood_fraction=0.50,
)
```

In `detailed_cash_flow` mode, standing dry wood at the horizon can also receive
a discounted residual value:

```python
economic_parameters = {
    ...,
    "terminal_value_per_dry_t": {
        tm.PINUS: 35.0,
        tm.EUCALYPTUS: 40.0,
    },
}
```

The economic tables report `discounted_gross_revenue`,
`discounted_terminal_value`, `discounted_total_income`,
`discounted_total_cost`, and `economic_value` separately.

## Execution times and green-up event conflicts

Every extracted mathematical-model solution reports:

- `model_build_time_seconds`;
- `solve_time_seconds`;
- `total_model_time_seconds`;
- `number_of_solver_calls`.

User-facing three-objective outputs use `greenup_event_conflict_count`. The old
`spatial_conflict_value` name is retained as a compatibility alias.

The three-objective epsilon routine avoids redundant spatial MILP solves. It
reuses the global economic anchor whenever it satisfies the requested bounds,
reuses the lexicographic minimum-green-up anchor for the exact minimum-conflict
bound, and can reuse previously solved looser epsilon models when their optimum
remains feasible under stricter bounds. The output column `solution_source`
distinguishes `reused_economic_anchor`, `reused_greenup_anchor`,
`reused_cached_epsilon_solution`, and `new_epsilon_solve`. DataFrame attributes
report requested combinations, new solves, reused solutions, avoided solver
calls, infeasible combinations, and aggregate timing.

## Three-objective knee point

`identify_three_objective_knee_point()` normalizes NPV, carbon stock-time, and
green-up event conflicts and identifies the solution with the greatest distance
toward the ideal point from the hyperplane through the three single-objective
anchors. The example notebook combines this with a triangulated Plotly surface
and exports a standalone interactive HTML figure.

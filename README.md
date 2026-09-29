# Treemün

**Growth-and-yield simulation and harvest-scheduling optimization for plantation forests, in Python.**

[![PyPI](https://img.shields.io/pypi/v/treemun-sim.svg)](https://pypi.org/project/treemun-sim/)
[![Python](https://img.shields.io/pypi/pyversions/treemun-sim.svg)](https://pypi.org/project/treemun-sim/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/fulloaf/treemun/blob/main/LICENSE)
[![Documentation](https://readthedocs.org/projects/treemun/badge/?version=latest)](https://treemun.readthedocs.io/)
[![Paper](https://img.shields.io/badge/Ecological%20Informatics-10.1016%2Fj.ecoinf.2026.104044-2a78d6.svg)](https://doi.org/10.1016/j.ecoinf.2026.104044)
[![Zenodo](https://img.shields.io/badge/Zenodo-10.5281%2Fzenodo.21801110-1682d4.svg)](https://doi.org/10.5281/zenodo.21801110)

Treemün connects published growth trajectories for Chilean *Pinus radiata* and *Eucalyptus globulus* plantations to landscape-level management decisions. In one workflow it:

1. **simulates** every feasible stand–policy trajectory (thinning, final harvest, regeneration, multiple rotations) in Mg of dry aboveground biomass;
2. **evaluates** each trajectory economically (gross revenue, net unit value, or a full discounted cash flow) and in terms of standing-carbon stock-time;
3. **optimizes** the landscape plan as a mixed-integer program: single-objective, weighted-sum, or ε-constraint, with optional even-flow, ending-stock, adjacency and green-up constraints;
4. **exports** the selected plan to GIS (GeoPackage) for mapping.

The framework and its benchmarks are described in [Ulloa-Fierro et al. (2026), *Ecological Informatics* 99, 104044](https://doi.org/10.1016/j.ecoinf.2026.104044).

📖 **Full user manual: [treemun.readthedocs.io](https://treemun.readthedocs.io/)**

<p align="center">
  <img src="https://raw.githubusercontent.com/fulloaf/treemun/main/docs/assets/paper_fig5_architecture.png" alt="Treemün data-flow architecture: inputs (stand inventory, management policies, lookup table, optional geometry) flow through data, simulation, economic, carbon, optimization, spatial-constraint and spatial modules to tabular, analytical, GIS-ready and reproducible outputs." width="620">
  <br><sub>Data-flow architecture of Treemün 2.0.0. Reproduced from Ulloa-Fierro et al. (2026), Fig. 5 (CC BY-NC-ND 4.0).</sub>
</p>

---

## Contents

- [Installation](#installation)
- [Quickstart: a 105-stand landscape in five steps](#quickstart-a-105-stand-landscape-in-five-steps)
- [What Treemün can do](#what-treemün-can-do)
- [Scope of the growth models](#scope-of-the-growth-models)
- [Input data](#input-data)
- [Units and conventions](#units-and-conventions)
- [Reproducing the paper](#reproducing-the-paper)
- [How to cite](#how-to-cite)

---

## Installation

Treemün requires Python 3.10 or later.

```bash
# Simulation, economics and carbon only (NumPy + pandas)
pip install treemun-sim

# Everything: optimization (Pyomo + HiGHS) and spatial tools (GeoPandas)
pip install "treemun-sim[complete]"
```

| Extra | Adds | Use it for |
|---|---|---|
| *(none)* | NumPy, pandas | simulation, economic and carbon accounting |
| `optimization` | Pyomo, HiGHS (`highspy`) | harvest-scheduling models |
| `spatial` | GeoPandas, Shapely, pyogrio | adjacency, green-up, GeoPackage export |
| `complete` | all of the above | the full workflow |
| `cplex` | Pyomo, IBM CPLEX Community Edition | CPLEX users (licence limits apply) |

HiGHS is installed as a Python package and works out of the box. CBC and a licensed CPLEX are also supported when available on your system; see the [installation guide](https://treemun.readthedocs.io/en/latest/getting-started/installation/) for Conda environments and solver setup.

---

## Quickstart: a 105-stand landscape in five steps

The package ships with the landscape used in the paper: 105 stands (30 *P. radiata*, 75 *E. globulus*, 834 ha) in the Biobío Region of Chile. Download [`forest_stands.csv`](https://github.com/fulloaf/treemun/raw/main/examples/forest_stands.csv) and [`treemun_landscape.gpkg`](https://github.com/fulloaf/treemun/raw/main/examples/treemun_landscape.gpkg), or clone the repository and run the code from its root.

### 1. Simulate every feasible stand–policy trajectory

```python
import treemun_sim as tm

forest, policy_summary, ending_stock, harvest, carbon = tm.simulate_forest(
    stands_file="examples/forest_stands.csv",
    horizon=30,                          # years
    include_carbon=True,
    return_carbon_for_optimization=True,
)

print(len(forest))                       # 780 stand–policy alternatives
```

Each element of `forest` is a pandas DataFrame with one row per year: stand age, operation (`none`, `thinning`, `final_harvest`), standing dry biomass before and after the operation, harvested biomass, carbon, and diagnostics. By default pine stands are offered 16 thinning/harvest-age combinations and eucalyptus stands 4 rotation ages; pass `pinus_policies=` or `eucalyptus_policies=` to change them.

<p align="center">
  <img src="https://raw.githubusercontent.com/fulloaf/treemun/main/docs/assets/stand_trajectories.png" alt="Two stand trajectories over 30 years. Left: a 73.3-ha Pinus radiata stand thinned at age 12 and harvested at 24, with the thinning drop and the new rotation. Right: a 17.5-ha Eucalyptus globulus stand harvested every 10 years, giving three rotations." width="900">
</p>

### 2. Put a price on each alternative

```python
economics = {
    "revenue_per_dry_t":            {tm.PINUS: 44.07, tm.EUCALYPTUS: 43.66},
    "transport_cost_per_dry_t":     {tm.PINUS: 15.76, tm.EUCALYPTUS: 10.59},
    "thinning_cost_per_dry_t":      {tm.PINUS: 11.03, tm.EUCALYPTUS: 0.0},
    "final_harvest_cost_per_dry_t": {tm.PINUS: 12.61, tm.EUCALYPTUS: 8.47},
    "replanting_cost_per_ha":       {tm.PINUS: 684.0, tm.EUCALYPTUS: 716.0},
    "annual_management_cost_per_ha": 15.0,
    "terminal_value_per_dry_t":     {tm.PINUS: 7.85, tm.EUCALYPTUS: 12.30},
}

evaluation = tm.evaluate_forest_economics(
    forest,
    economic_mode="detailed_cash_flow",   # true NPV
    discount_rate=0.08,
    economic_parameters=economics,
)
evaluation.summary_by_policy.head()       # NPV and every cost component, per stand–policy
```

These are the illustrative 2025 USD values of the paper (Table B.3). All prices and costs are scenario inputs: replace them with your own.

### 3. Find the NPV-maximizing landscape plan

```python
model_options = dict(
    policy_summary=policy_summary,
    ending_dry_wood_by_policy=ending_stock,
    harvested_dry_wood_by_period=harvest,
    carbon_stock_time_by_period=carbon,
    forest=forest,
    horizon=30,
    economic_mode="detailed_cash_flow",
    economic_parameters=economics,
    discount_rate=0.08,
    even_flow_mode="none",
)

model = tm.build_forest_management_model(**model_options, objective="economic")
results = tm.solve_model(model, "appsi_highs")
solution = tm.extract_solution(model, results)

print(f"NPV:               {solution['economic_value']:,.0f} USD")                     # ≈ 2,596,065
print(f"Carbon stock-time: {solution['carbon_stock_time_tC_year']:,.0f} Mg C·yr")     # ≈ 873,049
print(f"Ending stock:      {solution['ending_dry_wood_t']:,.0f} Mg")                  # ≈ 29,331

solution["selected_policies"]    # one row per stand: chosen policy, thinning and harvest ages
solution["harvest_schedule"]     # dry biomass harvested each year
```

### 4. Explore the NPV–carbon trade-off

```python
payoff = tm.build_biobjective_payoff_table(
    solver_name="appsi_highs", model_options=model_options,
)
front = tm.build_weighted_pareto_front(
    weights=[0.0, 0.25, 0.5, 0.75, 1.0],
    solver_name="appsi_highs",
    model_options=model_options,
    payoff_table=payoff,
)
front[["npv_weight", "economic_value", "carbon_stock_time_tC_year"]]
```

<p align="center">
  <img src="https://raw.githubusercontent.com/fulloaf/treemun/main/docs/assets/npv_carbon_front.png" alt="NPV against standing-carbon stock-time for the 105-stand landscape. Weighted-sum and epsilon-constraint solutions trace a concave frontier from the economic anchor (2.596 million USD, 0.87 million Mg C·yr) to the carbon anchor (2.472 million USD, 1.18 million Mg C·yr)." width="620">
</p>

On this landscape the carbon-maximizing plan holds 35% more carbon stock-time than the NPV-maximizing plan for less than 5% lower NPV, and the equal-weight compromise gains 20% carbon for about 1% of NPV.

### 5. Map the plan

```python
tm.export_optimal_solution_to_geopackage(
    forest=forest,
    solution=solution,
    geometry_file="examples/treemun_landscape.gpkg",
    output_file="npv_optimal_plan.gpkg",
)
```

Open the GeoPackage in QGIS or GeoPandas: one feature per stand and year, with the selected policy and all trajectory variables.

<p align="center">
  <img src="https://raw.githubusercontent.com/fulloaf/treemun/main/docs/assets/landscape_maps.png" alt="Two maps of the 105-stand landscape. Left: stands coloured by species. Right: the NPV-optimal plan, with stands shaded by the period of their first final harvest." width="900">
</p>

---

## What Treemün can do

| Capability | Main functions | Manual |
|---|---|---|
| Event-based stand simulation for pine (two-state) and eucalyptus (one-state) | `simulate_forest`, `forest_to_long_table` | [Simulation](https://treemun.readthedocs.io/en/latest/guide/simulation/) |
| Three economic accounting scopes: gross revenue, net unit value, detailed cash flow (NPV) | `evaluate_forest_economics` | [Economics](https://treemun.readthedocs.io/en/latest/guide/economics/) |
| Standing-carbon stock and stock-time coefficients | `simulate_forest(include_carbon=True)`, `add_carbon_accounting` | [Carbon](https://treemun.readthedocs.io/en/latest/guide/carbon/) |
| Single-objective MILP with ending-stock, terminal-value and even-flow options | `build_forest_management_model`, `solve_model`, `extract_solution` | [Optimization](https://treemun.readthedocs.io/en/latest/guide/optimization/) |
| NPV–carbon trade-offs: payoff table, normalized weighted sum, ε-constraint | `build_biobjective_payoff_table`, `build_weighted_pareto_front`, `build_epsilon_constraint_front` | [Multi-objective](https://treemun.readthedocs.io/en/latest/guide/multiobjective/) |
| Adjacency and green-up constraints (hard, soft, or as a third objective) | `build_adjacency_edges`, `add_greenup_adjacency`, `build_three_objective_epsilon_front`, `identify_three_objective_knee_point` | [Spatial planning](https://treemun.readthedocs.io/en/latest/guide/spatial/) |
| GIS export of all alternatives or of the selected plan | `export_simulation_to_geopackage`, `export_optimal_solution_to_geopackage` | [GIS export](https://treemun.readthedocs.io/en/latest/guide/gis-export/) |
| Migration of Treemün 1.x input files | `convert_v1_stand_file` | [Migration](https://treemun.readthedocs.io/en/latest/reference/migration/) |

### How a stand is simulated

Pine stands move through a two-state machine: they grow on a *pre-thinning* curve until the thinning age, switch to the linked *post-thinning* curve, and restart at age 1 after final harvest. Eucalyptus stands follow a single curve per rotation.

<p align="center">
  <img src="https://raw.githubusercontent.com/fulloaf/treemun/main/docs/assets/paper_fig2_state_logic.png" alt="Flow diagrams of the simulation logic: (a) the common annual stand–policy loop; (b) the Pinus radiata two-state machine with pre-thinning and post-thinning states; (c) the Eucalyptus globulus one-state rotation." width="820">
  <br><sub>Simulation and state-transition logic. Reproduced from Ulloa-Fierro et al. (2026), Fig. 2 (CC BY-NC-ND 4.0).</sub>
</p>

The choice of policy changes timing, harvested volume and the stock left at the horizon:

<p align="center">
  <img src="https://raw.githubusercontent.com/fulloaf/treemun/main/docs/assets/policy_comparison.png" alt="Three panels for the same pine stand under three policies (thin at 10 and harvest at 18; thin at 11 and harvest at 22; thin at 12 and harvest at 24), showing different rotation timing, total harvest and ending stock." width="900">
</p>

### Spatial planning with three objectives

Adding the stand polygons lets Treemün count *green-up event conflicts*: adjacent stands harvested within a set number of years of each other. Conflicts can be forbidden, penalized, or minimized alongside NPV and carbon:

```python
edges = tm.build_adjacency_edges("examples/treemun_landscape.gpkg")
indicator = tm.build_final_harvest_indicator(forest)

payoff_3d = tm.build_three_objective_payoff_table(
    adjacency_edges=edges,
    final_harvest_indicator=indicator,
    greenup_window=2,
    biobjective_payoff_table=payoff,
    solver_name="appsi_highs",
    model_options=model_options,
)
front_3d = tm.build_three_objective_epsilon_front(
    adjacency_edges=edges,
    final_harvest_indicator=indicator,
    greenup_window=2,
    number_of_carbon_points=5,
    number_of_greenup_points=5,
    payoff_table=payoff_3d,
    solver_name="appsi_highs",
    model_options=model_options,
)
knee = tm.identify_three_objective_knee_point(front_3d, payoff_table=payoff_3d)
```

<p align="center">
  <img src="https://raw.githubusercontent.com/fulloaf/treemun/main/docs/assets/paper_fig9a_three_objective.jpg" alt="Three-dimensional scatter of nondominated solutions over NPV, carbon stock-time and green-up event conflicts, with a translucent interpolated surface and the geometric knee-like solution marked." width="620">
  <br><sub>Sampled three-objective ε-constraint approximation for the 105-stand landscape. Reproduced from Ulloa-Fierro et al. (2026), Fig. 9a (CC BY-NC-ND 4.0).</sub>
</p>

Spatial models are much harder to solve than non-spatial ones: the full 5 × 5 grid above took about 72 minutes with CPLEX in the paper. Start with a coarse grid.

---

## Scope of the growth models

Treemün implements 34 continuous surrogate functions of dry aboveground biomass, fitted to published Chilean production tables (INSIGNE, EUCASIM and associated studies). They reproduce those tables with R² = 0.9982 and RMSE = 6.38 Mg ha⁻¹.

| Dimension | *Pinus radiata* | *Eucalyptus globulus* |
|---|---|---|
| Geographical zones | 6 and 7 | 1 and 2 |
| Site index (m at age 10) | 23, 26, 29, 32 | 24, 26, 28, 30, 32 |
| Initial density (trees ha⁻¹) | 1250 | 800 or 1250 |
| Management regime | pulpwood, multipurpose, intensive-1, intensive-2 | none (unthinned) |
| Growth-curve states | unthinned, pre-thinning, linked post-thinning | unthinned |
| Surrogate equations | 14 | 20 |

In version 2.0.0 every pine input stand must start on a pre-thinning curve linked to a post-thinning curve, so the two unthinned *pulpwood* equations are distributed in the lookup table but are not accepted as initial stand conditions.

The equations describe the source tables, not independent field validation. Stands outside these strata need new source tables or recalibrated coefficients, which you can supply through your own lookup table (`lookup_table_file=`).

---

## Input data

A stand table is a CSV with one row per stand:

| Column | Example | Meaning |
|---|---|---|
| `stand_id` | `stand65` | unique identifier, also the join key to geometries |
| `area_ha` | `95.869` | stand area in hectares |
| `species` | `Pinus radiata` | `Pinus radiata` or `Eucalyptus globulus` |
| `initial_age` | `14` | biological age at the start of the horizon (years) |
| `zone` | `6` | growth zone |
| `site_index` | `32` | site index |
| `management_regime` | `intensive_1` | pine: `multipurpose`, `intensive_1`, `intensive_2`; eucalyptus: `none` |
| `growth_curve` | `pre_thinning_1250_700` | `unthinned` or `pre_thinning_1250_700` |
| `initial_density_trees_ha` | `1250` | initial planting density |

Every row must match exactly one equation in the lookup table; Treemün validates inputs before simulating and reports the offending rows. Pine stands always start on a pre-thinning curve. If a policy's thinning age is already past, Treemün harvests the stand in year 1 and starts a new rotation. Geometries (optional) are a GeoPackage or Shapefile in a projected CRS with one polygon per `stand_id`.

See [Input data](https://treemun.readthedocs.io/en/latest/guide/input-data/) for the full schema and the lookup-table format.

---

## Units and conventions

- Biomass is **Mg (metric tonnes) of dry aboveground biomass**; column names use `_t` (for example `harvested_dry_wood_t`).
- Carbon is standing aboveground live carbon, `C = carbon fraction × dry biomass` (0.48 for pine, 0.51 for eucalyptus by default), in Mg C (`_tC`).
- The carbon objective is **stock-time**: the sum over years of standing carbon, in Mg C·yr. It measures how much carbon is held and for how long; it is not a full greenhouse-gas balance (roots, soil, dead wood, wood products and emissions are excluded).
- Monetary values are in whatever currency and base year your parameters use.

---

## Reproducing the paper

| Material | Location |
|---|---|
| Complete 105-stand workflow (all economic modes, fronts, green-up, knee point, GIS export) | [`examples/Treemun_2_0_0_full_105_stands_analysis.ipynb`](https://github.com/fulloaf/treemun/blob/main/examples/Treemun_2_0_0_full_105_stands_analysis.ipynb) |
| Surrogate vs. source-table and solver benchmarks | [`benchmark_notebooks_and_generator/`](https://github.com/fulloaf/treemun/tree/main/benchmark_notebooks_and_generator) |
| Conda environments (CBC + HiGHS, optional CPLEX) | `environment.yml`, `environment-cplex.yml` |
| Archived release | [Zenodo, 10.5281/zenodo.21801110](https://doi.org/10.5281/zenodo.21801110) |

Upgrading from Treemün 1.x? Units changed from m³ to Mg of dry biomass and the API moved to English: see [`MIGRATION_1_TO_2.md`](https://github.com/fulloaf/treemun/blob/main/MIGRATION_1_TO_2.md).

---

## How to cite

If you use Treemün, please cite the article:

> Ulloa-Fierro, F., Álvarez-Miranda, E., Garcia-Gonzalo, J., González-Olabarria, J. R., Mola-Yudego, B., Miranda, A., Carrasco-Barra, J., & Weintraub, A. (2026). Treemün: A Python framework for spatial growth-and-yield simulation and harvest scheduling optimization in plantation forests. *Ecological Informatics*, 99, 104044. https://doi.org/10.1016/j.ecoinf.2026.104044

```bibtex
@article{UlloaFierro2026Treemun,
  title   = {Treem{\"u}n: A Python framework for spatial growth-and-yield simulation
             and harvest scheduling optimization in plantation forests},
  author  = {Ulloa-Fierro, Felipe and {\'A}lvarez-Miranda, Eduardo and
             Garcia-Gonzalo, Jordi and Gonz{\'a}lez-Olabarria, Jos{\'e} Ram{\'o}n and
             Mola-Yudego, Blas and Miranda, Alejandro and
             Carrasco-Barra, Jaime and Weintraub, Andr{\'e}s},
  journal = {Ecological Informatics},
  volume  = {99},
  pages   = {104044},
  year    = {2026},
  doi     = {10.1016/j.ecoinf.2026.104044}
}
```

## Licence and contact

Treemün is released under the [MIT licence](https://github.com/fulloaf/treemun/blob/main/LICENSE). Figures marked "Reproduced from Ulloa-Fierro et al. (2026)" are © The Authors, published by Elsevier under [CC BY-NC-ND 4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/).

Bug reports and feature requests: [GitHub issues](https://github.com/fulloaf/treemun/issues). Maintainer: Felipe Ulloa-Fierro ([ORCID 0009-0002-3873-2605](https://orcid.org/0009-0002-3873-2605)).

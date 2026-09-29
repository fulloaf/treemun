# Quickstart

This page runs the complete Treemün workflow on the landscape used in the paper: **105 stands (30 *Pinus radiata*, 75 *Eucalyptus globulus*, 834.27 ha) in the Biobío Region of Chile, planned over 30 years.** Every number shown below is what the code returns.

You need the full installation (`pip install "treemun-sim[complete]"`) and the two example files from the repository:

- [`examples/forest_stands.csv`](https://github.com/fulloaf/treemun/raw/main/examples/forest_stands.csv): the stand inventory;
- [`examples/treemun_landscape.gpkg`](https://github.com/fulloaf/treemun/raw/main/examples/treemun_landscape.gpkg): the stand polygons (only for step 6).

Run the code from the repository root, or adjust the paths.

<figure markdown="span">
  ![Example landscape and NPV-optimal plan](../assets/landscape_maps.png)
  <figcaption>Left: the 105 stands by species. Right: the NPV-optimal plan from step 4, shaded by the year of each stand's first final harvest.</figcaption>
</figure>

## 1. Load and inspect the stands

```python
import treemun_sim as tm

stands = tm.load_stand_table("examples/forest_stands.csv")
stands.groupby("species")["area_ha"].agg(["count", "sum"])
```

```text
                     count      sum
species
Eucalyptus globulus     75  302.536
Pinus radiata           30  531.733
```

`load_stand_table` checks the columns, types and identifiers and fails with an explicit message if anything is wrong. See [Input data](../guide/input-data.md).

## 2. Simulate all stand–policy alternatives

```python
forest, policy_summary, ending_stock, harvest, carbon = tm.simulate_forest(
    stands_file="examples/forest_stands.csv",
    horizon=30,
    include_carbon=True,
    return_carbon_for_optimization=True,
)

print(len(forest))                            # 780 alternatives
print(sum(len(frame) for frame in forest))    # 23,400 annual rows
```

With the default policy catalogue, each pine stand is simulated under 16 thinning/final-harvest age pairs and each eucalyptus stand under 4 rotation ages. Policies that are infeasible for a stand are dropped, leaving 780 alternatives.

The five returned objects are:

| Object | Type | Content |
|---|---|---|
| `forest` | list of DataFrames | one annual trajectory per stand–policy |
| `policy_summary` | list of dicts | stand, policy, thinning age, final-harvest age, initial equation |
| `ending_stock` | dict `(stand, policy) → Mg` | dry biomass standing at the end of the horizon |
| `harvest` | dict `(period, species, policy, stand) → Mg` | harvested dry biomass (only non-zero entries) |
| `carbon` | dict `(period, species, policy, stand) → Mg C·yr` | carbon stock-time coefficients |

To look at everything as one table:

```python
long = tm.forest_to_long_table(forest)
long.groupby("operation").size()
```

```text
operation
final_harvest     1689
none             21048
thinning           663
```

## 3. Evaluate the economics

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
    economic_mode="detailed_cash_flow",
    discount_rate=0.08,
    economic_parameters=economics,
)
evaluation.summary_by_policy[
    ["stand_id", "policy", "discounted_total_income", "discounted_total_cost", "economic_value"]
].head()
```

`summary_by_policy` has one row per alternative with every discounted revenue and cost component; `cash_flow_table` has the same information per year. The values are the illustrative 2025 USD scenario of the paper; see [Economics](../guide/economics.md) for all parameters.

## 4. Optimize the landscape plan

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
```

```python
solution["economic_value"]              # 2,596,065  USD (NPV)
solution["carbon_stock_time_tC_year"]   #   873,049  Mg C·yr
solution["ending_dry_wood_t"]           #    29,331  Mg
```

!!! warning "Set `even_flow_mode` explicitly"
    The default is `even_flow_mode="two_sided_average"` with a ±10% tolerance. On this landscape even-flow is infeasible for every tolerance up to 100% (see [Optimization](../guide/optimization.md#even-flow)), so the examples switch it off with `"none"`.

`solution` is a dictionary. The most useful entries:

| Key | Content |
|---|---|
| `economic_value`, `economic_metric` | objective value and what it measures (`net_present_value` here) |
| `carbon_stock_time_tC_year` | carbon stock-time of the selected plan |
| `ending_dry_wood_t` | dry biomass left at the horizon |
| `selected_policies` | DataFrame, one row per stand with the chosen policy |
| `harvest_schedule` | DataFrame, harvested dry biomass per year |
| `selected_economic_summary`, `selected_economic_cash_flow` | economic detail of the chosen alternatives |
| `model_build_time_seconds`, `solve_time_seconds` | timing |

## 5. Trade NPV against carbon

```python
payoff = tm.build_biobjective_payoff_table(
    solver_name="appsi_highs", model_options=model_options,
)
payoff[["optimized_for", "economic_value", "carbon_stock_time_tC_year", "ending_dry_wood_t"]]
```

| optimized_for | economic_value | carbon_stock_time_tC_year | ending_dry_wood_t |
|---|---:|---:|---:|
| economic | 2,596,065 | 873,049 | 29,331 |
| carbon | 2,471,946 | 1,179,847 | 79,394 |

```python
weighted = tm.build_weighted_pareto_front(
    weights=[0.0, 0.25, 0.5, 0.75, 1.0],
    solver_name="appsi_highs",
    model_options=model_options,
    payoff_table=payoff,
)
epsilon = tm.build_epsilon_constraint_front(
    epsilon_objective="carbon",
    number_of_points=7,
    payoff_table=payoff,
    solver_name="appsi_highs",
    model_options=model_options,
)
```

| npv_weight | economic_value | carbon_stock_time_tC_year |
|---:|---:|---:|
| 0.00 | 2,471,946 | 1,179,847 |
| 0.25 | 2,502,770 | 1,169,802 |
| 0.50 | 2,568,691 | 1,051,085 |
| 0.75 | 2,593,391 | 910,033 |
| 1.00 | 2,596,065 | 873,049 |

<figure markdown="span">
  ![NPV–carbon trade-off](../assets/npv_carbon_front.png){ width="620" }
  <figcaption>Weighted-sum (7 weights) and ε-constraint (7 carbon thresholds) approximations of the NPV–carbon trade-off.</figcaption>
</figure>

The equal-weight plan raises carbon stock-time by 20% relative to the economic optimum for about 1% less NPV. See [Multi-objective analysis](../guide/multiobjective.md).

## 6. Export and map

```python
tm.export_optimal_solution_to_geopackage(
    forest=forest,
    solution=solution,
    geometry_file="examples/treemun_landscape.gpkg",
    output_file="npv_optimal_plan.gpkg",
    layer="optimal_solution",
)
```

The layer has one feature per stand and year with the selected policy and all trajectory variables. Filter by `period` in QGIS, or in GeoPandas:

```python
import geopandas as gpd

plan = gpd.read_file("npv_optimal_plan.gpkg", layer="optimal_solution")
plan.query("period == 1").plot(column="operation", legend=True)
```

## Next steps

- Add adjacency and green-up constraints: [Spatial planning](../guide/spatial.md).
- Compare economic accounting scopes and terminal treatments: [Economics](../guide/economics.md).
- Run the full analysis of the paper: [`examples/Treemun_2_0_0_full_105_stands_analysis.ipynb`](https://github.com/fulloaf/treemun/blob/main/examples/Treemun_2_0_0_full_105_stands_analysis.ipynb).

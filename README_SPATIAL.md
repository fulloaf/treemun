# Treemün 2.0 spatial workflow

Treemün 2.0 uses `stand_id` as the spatial join key and GeoPackage as the preferred output format.

## Geometry input

The example geometry file is:

```text
examples/treemun_landscape.gpkg
```

Its `stands` layer contains 105 projected stand polygons with English attribute names. User-supplied geometries must contain one unique polygon per `stand_id`.

## Export all simulated alternatives

```python
import treemun_sim as tm

forest, summary, ending_stock, harvest = tm.simulate_forest(
    stands_file="examples/forest_stands.csv",
    horizon=30,
)

tm.export_simulation_to_geopackage(
    forest=forest,
    geometry_file="examples/treemun_landscape.gpkg",
    output_file="outputs/treemun_simulation.gpkg",
    layer="simulation",
)
```

The output uses a long representation: one feature per stand, policy, and period. This avoids Shapefile field-name limits and preserves descriptive variable names such as `standing_dry_wood_t_after_operation`.

## Export the selected plan

```python
solution = tm.extract_solution(model, results)

tm.export_optimal_solution_to_geopackage(
    forest=forest,
    solution=solution,
    geometry_file="examples/treemun_landscape.gpkg",
    output_file="outputs/treemun_optimal.gpkg",
    layer="optimal_solution",
)
```

## Adjacency edges

```python
edges = tm.build_adjacency_edges(
    "examples/treemun_landscape.gpkg",
    minimum_shared_boundary=0.0,
)
```

The returned table contains:

```text
stand_id_a
stand_id_b
shared_boundary_length
```

A projected coordinate reference system is required because shared-boundary weights are measured in map units.

## Same-period final-harvest adjacency

```python
indicator = tm.build_final_harvest_indicator(forest)

tm.add_final_harvest_adjacency(
    model,
    adjacency_edges=edges,
    final_harvest_indicator=indicator,
    mode="hard",
)
```

For a soft formulation, use `mode="soft"` and specify `penalty`. Set `weight_by_shared_boundary=True` to weight each conflict by shared-boundary length.

## Green-up constraints

```python
tm.add_greenup_adjacency(
    model,
    adjacency_edges=edges,
    final_harvest_indicator=indicator,
    greenup_window=2,
    mode="hard",
)
```

With `greenup_window=2`, adjacent stands cannot select policies whose final harvests occur within two periods of each other.


## Spatial conflict as a third objective

`add_spatial_conflict_measure()` creates an exact conflict expression without replacing the active objective. A conflict is counted when adjacent stands select final-harvest periods separated by no more than `greenup_window`.

```python
model = tm.build_forest_management_model(
    **model_options,
    objective="npv",
)

tm.add_spatial_conflict_measure(
    model,
    adjacency_edges=edges,
    final_harvest_indicator=indicator,
    greenup_window=2,
)

# The expression can be constrained, minimized, or included in an external
# multiobjective procedure.
print(model.greenup_event_conflict_value)
```

## Three-objective epsilon front

Treemün can maximize the selected economic metric—NPV in detailed cash-flow mode—subject to a minimum standing-carbon stock-time and a maximum spatial-conflict value:

```python
payoff_3d = tm.build_three_objective_payoff_table(
    adjacency_edges=edges,
    final_harvest_indicator=indicator,
    greenup_window=2,
    solver_name="appsi_highs",
    solver_options={
        "relative_gap": 0.01,
        "threads": 8,
        "time_limit_seconds": None,
    },
    model_options=model_options,
)

front_3d = tm.build_three_objective_epsilon_front(
    adjacency_edges=edges,
    final_harvest_indicator=indicator,
    greenup_window=2,
    number_of_carbon_points=5,
    number_of_conflict_points=5,
    payoff_table=payoff_3d,
    solver_name="appsi_highs",
    solver_options={
        "relative_gap": 0.01,
        "threads": 8,
        "time_limit_seconds": None,
    },
    model_options=model_options,
    reuse_payoff_anchors=True,
    reuse_cached_solutions=True,
)
```

Before building a new spatial MILP, the epsilon routine checks whether a payoff
anchor or an already solved looser epsilon model is still feasible and therefore
provably optimal for the requested stricter bounds. `solution_source` records
where each point came from, while DataFrame attributes report how many solver
calls were avoided.

The result contains `economic_value` (plus the compatibility alias `npv_value`), `carbon_stock_time_tC_year`, and `greenup_event_conflict_count`, together with the selected policies for each nondominated point. See `examples/Treemun_2_0_0_full_105_stands_analysis.ipynb` for an interactive 3D visualization.


The previous `spatial_conflict_value` output remains available as a compatibility alias.

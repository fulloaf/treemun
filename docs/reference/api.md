# API reference

All public functions are available from the top-level package:

```python
import treemun_sim as tm
```

Parameters are keyword-only unless shown otherwise. Units follow the [conventions](../index.md#units-and-conventions): Mg of dry biomass (`_t`), Mg C (`_tC`), Mg C·yr (`_tC_year`).

## Data

::: treemun_sim.load_stand_table

::: treemun_sim.load_lookup_table

::: treemun_sim.convert_v1_stand_file

## Simulation

::: treemun_sim.simulate_forest

::: treemun_sim.forest_to_long_table

### Constants

| Name | Value |
|---|---|
| `tm.PINUS` | `"Pinus radiata"` |
| `tm.EUCALYPTUS` | `"Eucalyptus globulus"` |
| `tm.DEFAULT_PINUS_POLICIES` | 16 (thinning age, final-harvest age) pairs: thinning 9–12, harvest 18–24 |
| `tm.DEFAULT_EUCALYPTUS_POLICIES` | rotation ages 9, 10, 11, 12 |
| `tm.DEFAULT_FALLBACK_THINNING_FRACTION` | 0.30 |
| `tm.DEFAULT_MINIMUM_CURVE_RESIDUAL_FRACTION` | 0.10 |
| `tm.DEFAULT_RANDOM_SEED` | 5555 |

## Carbon

::: treemun_sim.add_carbon_accounting

::: treemun_sim.StandingWoodCarbonAccounting
    options:
      members: false

::: treemun_sim.SpeciesCarbonParameter
    options:
      members: false

| Name | Value |
|---|---|
| `tm.DEFAULT_SPECIES_CARBON_PARAMETERS` | pine 0.48, eucalyptus 0.51 |
| `tm.CO2E_FACTOR` | 44/12 |

## Economics

::: treemun_sim.evaluate_forest_economics

::: treemun_sim.EconomicEvaluation
    options:
      members: false

## Optimization

::: treemun_sim.build_forest_management_model

::: treemun_sim.solve_model

::: treemun_sim.extract_solution

## Multi-objective

::: treemun_sim.build_biobjective_payoff_table

::: treemun_sim.biobjective_normalization_from_payoff

::: treemun_sim.build_weighted_pareto_front

::: treemun_sim.build_epsilon_constraint_front

::: treemun_sim.filter_nondominated_points

## Spatial constraints

::: treemun_sim.build_adjacency_edges

::: treemun_sim.build_final_harvest_indicator

::: treemun_sim.add_greenup_adjacency

::: treemun_sim.add_final_harvest_adjacency

::: treemun_sim.add_spatial_conflict_measure

`add_greenup_event_conflict_measure` is an alias of `add_spatial_conflict_measure`.

::: treemun_sim.count_greenup_event_conflicts

`count_greenup_adjacency_conflicts` is an alias of `count_greenup_event_conflicts`.

## Three objectives

::: treemun_sim.build_three_objective_payoff_table

::: treemun_sim.build_three_objective_epsilon_front

::: treemun_sim.identify_three_objective_knee_point

## GIS export

::: treemun_sim.export_optimal_solution_to_geopackage

::: treemun_sim.export_simulation_to_geopackage

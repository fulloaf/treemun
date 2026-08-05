# Migrating from Treemün 1.x to 2.0

Treemün 2.0 is a major release because it corrects physical units, standardizes the API in English, and changes carbon accounting.

## Units

Growth-equation outputs are metric tonnes of dry wood per hectare. They are not cubic metres.

| Treemün 1.x concept | Treemün 2.0 field |
|---|---|
| standing quantity before an operation | `standing_dry_wood_t_before_operation` |
| removed quantity | `harvested_dry_wood_t` |
| remaining quantity | `standing_dry_wood_t_after_operation` |
| final remaining stock | `ending_dry_wood_t` |
| economic unit value | currency per tonne of dry wood |

## Growth curves

| Previous label | Canonical 2.0 label |
|---|---|
| `PostRaleo1250-700` | `pre_thinning_1250_700` |
| `post_thinning_1250_700` | `pre_thinning_1250_700` |
| `PostPodayRaleo700-300` | `post_thinning_700_300` |
| `post_pruning_thinning_700_300` | `post_thinning_700_300` |
| `SinManejo` | `unthinned` |

The new labels identify only whether the equation is used before or after thinning. Pruning is not a separate operation in Treemün.

## Stand columns

| Treemün 1.x | Treemün 2.0 |
|---|---|
| `id_rodal` | `stand_id` |
| `hectareas` | `area_ha` |
| `especie` | `species` |
| `edad_inicial` | `initial_age` |
| `zona` | `zone` |
| `manejo` | `management_regime` |
| `condicion` | `growth_curve` |
| `densidad_inicial` | `initial_density_trees_ha` |

Convert a file with:

```python
from treemun_sim import convert_v1_stand_file

convert_v1_stand_file("stands_v1.csv", "stands_v2.csv")
```

## Species and regimes

Canonical species names are `Pinus radiata` and `Eucalyptus globulus`. Canonical regimes are `none`, `intensive_1`, `intensive_2`, `multipurpose`, and `pulpwood`.

## Carbon

Carbon is calculated directly from dry wood:

```text
standing_wood_carbon_tC = standing_dry_wood_t * carbon_fraction
```

Wood density is not applied. The first carbon objective is post-operation standing-wood stock-time in `tC·year`.

## API

```python
# 1.x
forest, summary, final_stock, harvest = simular_bosque(
    archivo_rodales="stands.csv",
    horizonte=30,
)

# 2.0
forest, policy_summary, ending_stock, harvest = simulate_forest(
    stands_file="stands.csv",
    horizon=30,
)
```

The Spanish public API is not part of the 2.0 canonical interface. Data migration aliases remain isolated in `treemun_sim.compatibility`.


## Economic interpretation

Treemün 2.0 distinguishes `gross_revenue`, `net_unit_value`, and `detailed_cash_flow`. The former `pine_revenue_per_t` and `eucalyptus_revenue_per_t` arguments remain compatibility inputs, but new projects should pass `economic_mode` and `economic_parameters`. Only `detailed_cash_flow` should be described as net present value.

## Thinning transition

The simulator now uses the difference between linked pre- and post-thinning curves when the residual is plausible. When the post-thinning curve would leave an excessively small residual, a configurable fixed-fraction fallback is applied and subsequent periods preserve continuity through post-thinning curve increments.


## Mandatory Pinus initialization and overdue thinning

`Pinus radiata` stands must now enter the planning horizon through a pre-thinning equation whose `next_equation_id` references the corresponding post-thinning equation. Initial post-thinning states are rejected.

For a policy with `thinning_age < initial_age`, Treemün no longer infers that thinning occurred before the planning horizon. The complete initial stock is harvested in period 1, the rotation is reset, and period 2 starts at biological age 1 on the original pre-thinning equation. This change can alter the number of feasible alternatives and ensures that all policies for a stand share one observed initial stock.


## Solver runtime controls and three-objective reuse

`solve_model()` now accepts `threads` and `time_limit_seconds` in addition to
`relative_gap`. New projects can pass the same `solver_options` mapping through
all payoff and Pareto-front helpers. Leave `threads=None` to preserve the native
solver default, and do not request more threads than the CPUs allocated by the
cluster scheduler.

The three-objective epsilon routine now reuses payoff anchors and previously
solved looser epsilon optima whenever they remain feasible under stricter bounds.
Use `solution_source` and the returned DataFrame attributes to distinguish actual
MILP solves from reused optimal solutions.

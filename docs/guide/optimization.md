# Optimization

Once every alternative is simulated and valued, choosing the landscape plan is a **stand–policy selection problem**: pick exactly one policy per stand. Treemün builds it as a Pyomo mixed-integer program.

## The model

For each stand \(i\) and feasible policy \(j\), a binary variable \(x_{ij}\) equals 1 if the policy is selected:

\[
\sum_{j \in J_i} x_{ij} = 1 \qquad \forall i
\]

All coefficients (NPV, harvest, carbon, ending stock) are fixed parameters computed by the simulator, so the model is linear. The landscape objectives are

\[
Z_N(\mathbf{x}) = \sum_{i}\sum_{j} \text{NPV}_{ij}\, x_{ij},
\qquad
Z_C(\mathbf{x}) = \sum_{t}\sum_{i}\sum_{j} c_{ijt}\, x_{ij}.
\]

## Build, solve, extract

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
results = tm.solve_model(model, "appsi_highs", relative_gap=0.01)
solution = tm.extract_solution(model, results)
```

Keeping the shared arguments in one `model_options` dictionary is convenient: the [multi-objective](multiobjective.md) and [spatial](spatial.md) functions take the same dictionary.

### Objectives

| `objective` | Maximizes |
|---|---|
| `"economic"` (alias `"npv"`) | the economic metric of `economic_mode` |
| `"carbon"` | carbon stock-time \(Z_C\) |
| `"weighted"` | `npv_weight` × normalized economic value + `carbon_weight` × normalized carbon |

For weighted models prefer [`build_weighted_pareto_front`](multiobjective.md#weighted-sum), which normalizes both objectives by their payoff-table ranges.

### Custom economic coefficients

To use values computed elsewhere, pass them directly as a `{(stand_id, policy): value}` dictionary:

```python
model = tm.build_forest_management_model(
    **model_options,
    economic_value_by_policy=my_values,
    objective="economic",
)
```

## Terminal conditions

```python
# at least 25,000 Mg standing at the horizon
model = tm.build_forest_management_model(
    **model_options, objective="economic", minimum_ending_dry_wood_t=25_000,
)

# at least half of the initial landscape stock
model = tm.build_forest_management_model(
    **model_options, objective="economic", minimum_ending_dry_wood_fraction=0.5,
)
```

The fractional version needs `forest=` in the options, to compute the initial stock. A minimum ending carbon stock is also available with `minimum_ending_carbon_tC=` plus `ending_carbon_by_policy=`. See [Economics](economics.md#the-end-of-the-horizon) for how these compare with a terminal value.

## Even flow

Even-flow constraints limit year-to-year variation in the total harvest \(H_t\):

| `even_flow_mode` | Constraint for each year \(t\) (tolerance \(\delta\) = `even_flow_tolerance`) |
|---|---|
| `"none"` | no constraint |
| `"two_sided_average"` (**default**, \(\delta\) = 0.10) | \((1-\delta)\bar H \le H_t \le (1+\delta)\bar H\), with \(\bar H\) the average annual harvest |
| `"two_sided_consecutive"` | \((1-\delta) H_t \le H_{t+1} \le (1+\delta) H_t\) |
| `"nondecreasing"` | \(H_{t+1} \ge (1-\delta) H_t\) |

!!! warning "Even flow can be infeasible"
    Feasibility depends on the initial age structure and the policy catalogue. On the 105-stand example, `"two_sided_average"` is infeasible for **every** tolerance from 25% to 100%: in some years no combination of stand schedules can deliver a strictly positive harvest. Because it is the default, set `even_flow_mode` explicitly, and check the termination condition when you use it:

    ```python
    results = tm.solve_model(model, "appsi_highs")
    status = str(results.solver.termination_condition).lower()
    if status in {"optimal", "feasible"}:
        solution = tm.extract_solution(model, results)
    else:
        print("No feasible plan:", status)
    ```

## What `extract_solution` returns

| Key | Content |
|---|---|
| `economic_metric`, `economic_value` | what the economic criterion measures, and its value |
| `net_present_value` | the NPV (only in `detailed_cash_flow` mode, otherwise `None`) |
| `carbon_stock_time_tC_year` | carbon stock-time of the plan |
| `ending_dry_wood_t`, `ending_carbon_tC` | stock at the horizon |
| `selected_policies` | DataFrame: stand, species, area, chosen policy, thinning and harvest ages, ending stock, economic value |
| `harvest_schedule` | DataFrame: harvested dry biomass per year |
| `selected_economic_summary`, `selected_economic_cash_flow` | economic detail of the chosen alternatives |
| `normalized_economic_value`, `normalized_carbon_value` | objective values on the normalized scale |
| `greenup_event_conflict_count` | green-up conflicts (spatial models only) |
| `model_build_time_seconds`, `solve_time_seconds`, `total_model_time_seconds`, `number_of_solver_calls` | timing |
| `solver_name`, `relative_gap_requested`, `threads_requested`, `time_limit_seconds_requested`, `solve_history` | run settings, for reproducibility |

`npv_value` is kept as an alias of `economic_value` for compatibility; new code should use `economic_value` and `economic_metric`.

## Solvers

HiGHS, CBC and CPLEX return the same solution on the 105-stand model. In the paper's single-thread benchmark on the normalized 0.5/0.5 NPV–carbon model, the median solve times were 0.025 s (CPLEX), 0.062 s (HiGHS) and 0.038 s (CBC); building the model took most of the ~1.9 s total. Differences between solvers matter much more for [spatial models](spatial.md).

See [Installation](../getting-started/installation.md#solvers) for solver names and runtime options.

# Economics

`evaluate_forest_economics` puts a value on each stand–policy trajectory. The same calculation feeds the optimizer, so you can inspect every coefficient before solving anything.

```python
evaluation = tm.evaluate_forest_economics(
    forest,
    economic_mode="detailed_cash_flow",
    discount_rate=0.08,
    economic_parameters=economics,
)

evaluation.economic_metric       # 'net_present_value'
evaluation.summary_by_policy     # one row per stand–policy, all discounted components
evaluation.cash_flow_table       # one row per stand–policy–year
evaluation.value_by_policy       # {(stand_id, policy): value}, used by the optimizer
```

## Three accounting scopes

Choose the scope that matches the data you have. They produce different numbers because they measure different things.

| `economic_mode` | Metric | Cash flow in year \(t\) | Parameters used |
|---|---|---|---|
| `gross_revenue` | `discounted_revenue` | harvested Mg × revenue per Mg | `revenue_per_dry_t` |
| `net_unit_value` | `discounted_net_margin` | harvested Mg × net value per Mg | `net_value_per_dry_t` |
| `detailed_cash_flow` | `net_present_value` | revenue − all costs (+ terminal value) | all parameters below |

Only `detailed_cash_flow` is a true net present value. Every mode discounts year \(t\) by \((1 + r)^t\), with \(r\) = `discount_rate`:

\[
\text{NPV}_{ij} = \sum_{t=1}^{H} \frac{\text{Revenue}_{ijt} - \text{Cost}_{ijt}}{(1+r)^t} + \frac{TV_{ijH}}{(1+r)^H}
\]

On the 105-stand example with the paper's parameters and no terminal value, maximizing each scope gives USD 7.436 million (gross revenue), 3.205 million (net unit value) and 2.573 million (NPV), and the selected plans differ.

## Parameters

Pass a dictionary with any of these keys; omitted keys take the default. Unknown keys raise an error, so typos are caught.

| Key | Applied to | Default |
|---|---|---|
| `revenue_per_dry_t` | every harvested Mg | pine 9.0, eucalyptus 10.0 |
| `net_value_per_dry_t` | every harvested Mg (`net_unit_value` mode only) | pine 9.0, eucalyptus 10.0 |
| `variable_cost_per_dry_t` | every harvested Mg | 0 |
| `transport_cost_per_dry_t` | every harvested Mg | 0 |
| `thinning_cost_per_dry_t` | Mg removed by thinning | 0 |
| `final_harvest_cost_per_dry_t` | Mg removed by final harvest | 0 |
| `thinning_cost_per_ha` | stand area, in thinning years | 0 |
| `final_harvest_cost_per_ha` | stand area, in final-harvest years | 0 |
| `replanting_cost_per_ha` | stand area, after each final harvest | 0 |
| `replanting_delay_periods` | years between final harvest and replanting | 0 |
| `annual_management_cost_per_ha` | stand area, every year | 0 |
| `terminal_value_per_dry_t` | Mg standing at the horizon (`detailed_cash_flow` only) | 0 |

!!! warning "The defaults are placeholders"
    The default prices exist so the code runs. They are not calibrated to any market; always supply your own.

Each value can be:

=== "A number"

    ```python
    {"transport_cost_per_dry_t": 12.0}
    ```

=== "By species"

    ```python
    {"transport_cost_per_dry_t": {tm.PINUS: 15.76, tm.EUCALYPTUS: 10.59}}
    # "default" covers any species not listed
    {"transport_cost_per_dry_t": {tm.PINUS: 15.76, "default": 10.0}}
    ```

=== "By year"

    ```python
    # one value per planning year (length ≥ horizon)
    {"revenue_per_dry_t": [44.0] * 10 + [46.0] * 10 + [48.0] * 10}
    ```

=== "By species and year"

    ```python
    {"revenue_per_dry_t": {tm.PINUS: [44.0] * 30, tm.EUCALYPTUS: [43.0] * 30}}
    ```

Costs are not double-counted automatically: if harvest costs are expressed per Mg, leave the per-hectare operation costs at zero, and vice versa.

### The paper's scenario

The illustrative values used in the paper (constant 2025 USD, 8% real discount rate) are:

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
```

They define an example scenario, not constants of the framework.

## Reading the results

`summary_by_policy` columns come in undiscounted/discounted pairs: `gross_revenue` / `discounted_gross_revenue`, `transport_cost` / `discounted_transport_cost`, and so on, plus the totals `discounted_total_income`, `discounted_total_cost` and `economic_value`.

To follow one alternative year by year:

```python
cf = evaluation.cash_flow_table
cf[(cf["stand_id"] == "stand65") & (cf["policy"] == "pinus_policy_05")][
    ["period", "economic_event", "harvested_dry_wood_t",
     "discounted_gross_revenue", "discounted_transport_cost",
     "discounted_replanting_cost", "discounted_economic_value"]
]
```

## The end of the horizon

A finite horizon rewards cutting everything before it ends, because the forest left standing has no value in the objective. Treemün offers two remedies, which can be combined:

- **Terminal value**: `terminal_value_per_dry_t` prices the biomass standing at year \(H\) (only in `detailed_cash_flow` mode).
- **Minimum ending stock**: a constraint in the optimization model, as an absolute amount (`minimum_ending_dry_wood_t`) or as a fraction of the initial landscape stock (`minimum_ending_dry_wood_fraction`). See [Optimization](optimization.md#terminal-conditions).

The two are not equivalent: a terminal value *prices* the remaining forest, a stock requirement *enforces* a physical minimum. On the 105-stand example (initial stock 84,928 Mg):

| Terminal treatment | NPV (USD) | Carbon stock-time (Mg C·yr) | Ending stock (Mg) |
|---|---:|---:|---:|
| None | 2,573,022 | 843,730 | 17,625 |
| Ending stock ≥ 50% of initial | 2,546,970 | 873,845 | 42,468 |
| Terminal value | 2,596,065 | 873,049 | 29,331 |

Source: Ulloa-Fierro et al. (2026), Table 5.

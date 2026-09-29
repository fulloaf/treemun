# Carbon

Treemün tracks **standing aboveground live carbon** in every simulated year and summarizes it as **carbon stock-time**, which the optimizer can maximize or constrain.

```python
forest, policy_summary, ending_stock, harvest, carbon = tm.simulate_forest(
    stands_file="examples/forest_stands.csv",
    horizon=30,
    include_carbon=True,                    # add carbon columns to each trajectory
    return_carbon_for_optimization=True,    # return the coefficients as a 5th object
)
```

## From biomass to carbon

Carbon is dry biomass times a species-specific carbon fraction. No wood-density conversion is needed because the growth equations already give dry mass.

\[
C_{ijt} = \phi^{C}_{s}\, B^{\text{end}}_{ijt}
\]

| Species | Default \(\phi^{C}\) (Mg C per Mg dry matter) |
|---|---|
| *Pinus radiata* | 0.48 |
| *Eucalyptus globulus* | 0.51 |

Defaults follow Olmedo et al. (2020) for Chilean plantations. Override them with:

```python
forest, *_ = tm.simulate_forest(
    stands_file="examples/forest_stands.csv",
    include_carbon=True,
    carbon_parameters={tm.PINUS: 0.47, tm.EUCALYPTUS: 0.50},
)
```

Carbon is evaluated in every year, not only when something happens. Without an operation it is the carbon of the standing stock; after thinning, of the residual stock; after final harvest, zero.

## Carbon stock-time

The optimization indicator adds up standing carbon over the horizon, weighted by the length of each period \(\Delta_t\) (1 year by default, set with `period_years=`):

\[
Z_C = \sum_{t} C_{ijt}\, \Delta_t \qquad [\text{Mg C·yr}]
\]

It rewards plans that hold **more** carbon for **longer**. A stand holding 100 Mg C for 10 years contributes 1,000 Mg C·yr.

## Carbon columns

With `include_carbon=True` each trajectory gains:

| Column | Unit | Meaning |
|---|---|---|
| `dry_wood_carbon_fraction` | – | \(\phi^{C}\) used |
| `standing_wood_carbon_tC_before_operation` | Mg C | carbon before the year's operation |
| `harvested_wood_carbon_tC` | Mg C | carbon in removed biomass |
| `standing_wood_carbon_tC_after_operation` | Mg C | carbon after the operation |
| `standing_wood_co2e_t_after_operation` | Mg CO₂e | same, × 44/12 (`tm.CO2E_FACTOR`) |
| `carbon_stock_time_tC_year` | Mg C·yr | this year's contribution to \(Z_C\) |
| `cumulative_carbon_stock_time_tC_year` | Mg C·yr | running total |

Carbon can also be added to trajectories simulated without it:

```python
forest = tm.add_carbon_accounting(
    forest, species_parameters={tm.PINUS: 0.48, tm.EUCALYPTUS: 0.51}
)
```

When you pass your own fractions, include every species in the landscape: a missing species raises an error rather than falling back to a default.

## What the indicator does not include

Stock-time measures how much aboveground live carbon is retained in the landscape and for how long. It is **not** a greenhouse-gas balance or a direct estimate of climate mitigation. It excludes roots, soil, forest floor, dead wood, harvested-wood products, substitution effects, decomposition and operational emissions. Do not describe a plan as climatically better on this indicator alone.

The unit suffix `tC` in column names means metric tonnes (Mg) of carbon.

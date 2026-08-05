"""Public simulation workflow for Treemün 2.0."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from .carbon import SpeciesCarbonParameter, StandingWoodCarbonAccounting
from .data import (
    load_lookup_table,
    load_stand_table,
    validate_stands_against_lookup,
)
from .simulation import (
    DEFAULT_EUCALYPTUS_POLICIES,
    DEFAULT_FALLBACK_THINNING_FRACTION,
    DEFAULT_MINIMUM_CURVE_RESIDUAL_FRACTION,
    DEFAULT_PINUS_POLICIES,
    generate_random_stands,
    simulate_trajectories,
)

DEFAULT_RANDOM_SEED = 5555


def simulate_forest(
    stands_file: str | Path | None = None,
    *,
    pinus_policies: Sequence[tuple[int, int]] = DEFAULT_PINUS_POLICIES,
    eucalyptus_policies: Sequence[tuple[int]] = DEFAULT_EUCALYPTUS_POLICIES,
    horizon: int = 30,
    number_of_stands: int = 100,
    random_seed: int = DEFAULT_RANDOM_SEED,
    lookup_table_file: str | Path | None = None,
    include_carbon: bool = False,
    return_carbon_for_optimization: bool = False,
    carbon_parameters: Mapping[str, SpeciesCarbonParameter | float] | None = None,
    period_years: float = 1.0,
    fallback_thinning_fraction: float = DEFAULT_FALLBACK_THINNING_FRACTION,
    minimum_curve_residual_fraction: float = (
        DEFAULT_MINIMUM_CURVE_RESIDUAL_FRACTION
    ),
):
    """Simulate feasible stand-management trajectories.

    Growth-equation outputs are interpreted as metric tonnes of dry wood per
    hectare. Stand-level stocks and harvests are metric tonnes of dry wood.

    Returns four objects by default. When ``return_carbon_for_optimization`` is
    true, returns a fifth dictionary with annual standing-carbon stock-time
    coefficients in tC·year.

    Pinus stands must start from a pre-thinning equation with a valid
    ``next_equation_id``. The post-thinning equation is entered only after a
    simulated thinning operation. If the selected policy's thinning age is
    lower than the initial biological age, Treemün fully harvests the initial
    rotation in period 1 and starts period 2 at age 1 on the pre-thinning curve.

    At a simulated thinning, the simulator first compares the pre- and
    post-thinning curves. If the post-thinning curve would retain no more than
    ``minimum_curve_residual_fraction`` of the pre-thinning stock,
    ``fallback_thinning_fraction`` is harvested instead. Subsequent stocks keep
    the corrected residual and follow the increments of the post-thinning curve.
    """
    if return_carbon_for_optimization and not include_carbon:
        raise ValueError(
            "return_carbon_for_optimization=True requires include_carbon=True."
        )
    if int(horizon) < 1:
        raise ValueError("horizon must be at least one year.")

    np.random.seed(int(random_seed))
    random.seed(int(random_seed))

    lookup = load_lookup_table(lookup_table_file)
    if stands_file is None:
        stands = generate_random_stands(
            lookup,
            number_of_stands=int(number_of_stands),
            horizon=int(horizon),
            pinus_policies=pinus_policies,
            eucalyptus_policies=eucalyptus_policies,
            random_seed=int(random_seed),
        )
    else:
        stands = load_stand_table(stands_file)
    validate_stands_against_lookup(stands, lookup)

    forest, policy_summary, ending_stock, harvested_by_period = simulate_trajectories(
        stands,
        lookup,
        horizon=int(horizon),
        pinus_policies=pinus_policies,
        eucalyptus_policies=eucalyptus_policies,
        fallback_thinning_fraction=fallback_thinning_fraction,
        minimum_curve_residual_fraction=minimum_curve_residual_fraction,
    )

    carbon_stock_time_by_period = None
    if include_carbon:
        accounting = StandingWoodCarbonAccounting(
            carbon_parameters, period_years=period_years
        )
        forest = accounting.add_to_forest(forest)
        if return_carbon_for_optimization:
            carbon_stock_time_by_period = accounting.stock_time_coefficients(forest)

    if return_carbon_for_optimization:
        return (
            forest,
            policy_summary,
            ending_stock,
            harvested_by_period,
            carbon_stock_time_by_period,
        )
    return forest, policy_summary, ending_stock, harvested_by_period

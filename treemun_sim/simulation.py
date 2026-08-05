"""Forest trajectory simulation using dry-wood mass equations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

PINUS = "Pinus radiata"
EUCALYPTUS = "Eucalyptus globulus"

DEFAULT_PINUS_POLICIES: tuple[tuple[int, int], ...] = (
    (9, 18),
    (9, 20),
    (9, 22),
    (9, 24),
    (10, 18),
    (10, 20),
    (10, 22),
    (10, 24),
    (11, 18),
    (11, 20),
    (11, 22),
    (11, 24),
    (12, 18),
    (12, 20),
    (12, 22),
    (12, 24),
)

DEFAULT_EUCALYPTUS_POLICIES: tuple[tuple[int], ...] = (
    (9,),
    (10,),
    (11,),
    (12,),
)

DEFAULT_FALLBACK_THINNING_FRACTION = 0.30
DEFAULT_MINIMUM_CURVE_RESIDUAL_FRACTION = 0.10


@dataclass(frozen=True)
class ManagementPolicy:
    """Canonical management policy used by the simulator."""

    species: str
    policy_number: int
    thinning_age: int | None
    final_harvest_age: int

    @property
    def name(self) -> str:
        prefix = "pinus" if self.species == PINUS else "eucalyptus"
        return f"{prefix}_policy_{self.policy_number:02d}"


@dataclass(frozen=True)
class GrowthEquation:
    equation_id: int
    next_equation_id: int | None
    species: str
    growth_curve: str
    alpha: float
    beta: float
    gamma: float

    def dry_wood_t_ha(self, age: int) -> float:
        """Evaluate dry-wood mass in metric tonnes per hectare."""
        return max(self.alpha * float(age) ** self.beta + self.gamma, 0.0)


def _equation_from_row(row: pd.Series) -> GrowthEquation:
    next_id = row.get("next_equation_id")
    return GrowthEquation(
        equation_id=int(row["equation_id"]),
        next_equation_id=None if pd.isna(next_id) or next_id == "" else int(next_id),
        species=str(row["species"]),
        growth_curve=str(row["growth_curve"]),
        alpha=float(row["alpha"]),
        beta=float(row["beta"]),
        gamma=float(row["gamma"]),
    )


def validate_policies(
    pinus_policies: Sequence[tuple[int, int]],
    eucalyptus_policies: Sequence[tuple[int]],
) -> None:
    if not pinus_policies:
        raise ValueError("pinus_policies cannot be empty.")
    if not eucalyptus_policies:
        raise ValueError("eucalyptus_policies cannot be empty.")

    for policy in pinus_policies:
        if len(policy) != 2:
            raise ValueError(f"Pinus policy must be (thinning_age, final_harvest_age): {policy}")
        thinning_age, final_harvest_age = map(int, policy)
        if thinning_age < 1 or final_harvest_age < 1:
            raise ValueError(f"Policy ages must be positive: {policy}")
        if thinning_age >= final_harvest_age:
            raise ValueError(f"thinning_age must be lower than final_harvest_age: {policy}")

    for policy in eucalyptus_policies:
        if len(policy) != 1:
            raise ValueError(f"Eucalyptus policy must be (final_harvest_age,): {policy}")
        if int(policy[0]) < 1:
            raise ValueError(f"Policy age must be positive: {policy}")


def build_policy_catalog(
    pinus_policies: Sequence[tuple[int, int]],
    eucalyptus_policies: Sequence[tuple[int]],
) -> dict[str, list[ManagementPolicy]]:
    validate_policies(pinus_policies, eucalyptus_policies)
    return {
        PINUS: [
            ManagementPolicy(PINUS, number, int(thinning), int(final_harvest))
            for number, (thinning, final_harvest) in enumerate(pinus_policies, start=1)
        ],
        EUCALYPTUS: [
            ManagementPolicy(EUCALYPTUS, number, None, int(final_harvest))
            for number, (final_harvest,) in enumerate(eucalyptus_policies, start=1)
        ],
    }


def is_policy_feasible(
    species: str,
    initial_age: int,
    horizon: int,
    policy: ManagementPolicy,
) -> bool:
    """Return whether a policy can produce a meaningful trajectory.

    Pinus stands always enter the planning horizon on a pre-thinning growth
    equation. When the policy's thinning age is already lower than the
    observed initial biological age, Treemün treats that rotation as overdue:
    the complete initial stock is harvested in period 1 and the next rotation
    starts at biological age 1 on the same pre-thinning equation. Therefore,
    these policies remain feasible even when their nominal final-harvest age
    is also lower than the observed initial age.
    """
    initial_age = int(initial_age)
    horizon = int(horizon)

    if species == PINUS and policy.thinning_age is not None:
        if initial_age > policy.thinning_age:
            return horizon >= 1
        thinning_period = policy.thinning_age - initial_age + 1
        return thinning_period <= horizon

    if initial_age > policy.final_harvest_age:
        return False
    harvest_period = policy.final_harvest_age - initial_age + 1
    return harvest_period <= horizon


def kitral_class(species: str, age: int, managed: bool) -> str:
    """Return the KITRAL plantation fuel class for a simulated state."""
    if species == PINUS:
        if age <= 3:
            return "PL01" if not managed else "NoCode"
        if age <= 11:
            return "PL02" if not managed else "PL05"
        if age <= 17:
            return "PL03" if not managed else "PL06"
        return "PL04" if not managed else "PL07"
    if species == EUCALYPTUS:
        if age <= 3:
            return "PL08"
        if age <= 10:
            return "PL09"
        return "PL10"
    raise ValueError(f"Unsupported species: {species}")


def _lookup_initial_equation(stand: pd.Series, lookup: pd.DataFrame) -> GrowthEquation:
    mask = (
        lookup["species"].eq(stand["species"])
        & lookup["zone"].eq(int(stand["zone"]))
        & lookup["site_index"].eq(int(stand["site_index"]))
        & lookup["management_regime"].eq(stand["management_regime"])
        & lookup["growth_curve"].eq(stand["growth_curve"])
        & lookup["initial_density_trees_ha"].eq(
            int(stand["initial_density_trees_ha"])
        )
    )
    matches = lookup.loc[mask]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one lookup equation for stand {stand['stand_id']!r}; "
            f"found {len(matches)}."
        )
    return _equation_from_row(matches.iloc[0])


def _equation_by_id(equation_id: int | None, lookup: pd.DataFrame) -> GrowthEquation | None:
    if equation_id is None:
        return None
    matches = lookup.loc[lookup["equation_id"].eq(int(equation_id))]
    if len(matches) != 1:
        raise ValueError(f"Unknown or duplicate equation_id: {equation_id}")
    return _equation_from_row(matches.iloc[0])


def _validate_initial_growth_transition(
    stand: pd.Series,
    initial_equation: GrowthEquation,
    lookup: pd.DataFrame,
) -> GrowthEquation | None:
    """Validate the mandatory initial growth state and return its next curve.

    Pinus input stands must always reference a pre-thinning equation with a
    valid ``next_equation_id`` leading to a post-thinning equation. A
    post-thinning equation is an internal state reached only after a thinning
    operation simulated within the planning horizon; it is never a valid
    initial condition.
    """
    if str(stand["species"]) != PINUS:
        return None

    stand_id = str(stand["stand_id"])
    if not initial_equation.growth_curve.startswith("pre_thinning"):
        raise ValueError(
            f"Pinus stand {stand_id!r} must start from a pre-thinning growth "
            f"equation; received {initial_equation.growth_curve!r}."
        )
    if initial_equation.next_equation_id is None:
        raise ValueError(
            f"Initial Pinus equation {initial_equation.equation_id} for stand "
            f"{stand_id!r} must define next_equation_id."
        )

    next_equation = _equation_by_id(initial_equation.next_equation_id, lookup)
    if next_equation is None:
        raise ValueError(
            f"Initial Pinus equation {initial_equation.equation_id} for stand "
            f"{stand_id!r} has no valid next equation."
        )
    if next_equation.species != PINUS:
        raise ValueError(
            f"next_equation_id {next_equation.equation_id} for stand "
            f"{stand_id!r} must reference a Pinus equation."
        )
    if not next_equation.growth_curve.startswith("post_thinning"):
        raise ValueError(
            f"next_equation_id {next_equation.equation_id} for stand "
            f"{stand_id!r} must reference a post-thinning growth equation; "
            f"received {next_equation.growth_curve!r}."
        )
    return next_equation


def _validate_thinning_transition_parameters(
    fallback_thinning_fraction: float,
    minimum_curve_residual_fraction: float,
) -> tuple[float, float]:
    fallback_fraction = float(fallback_thinning_fraction)
    minimum_residual_fraction = float(minimum_curve_residual_fraction)

    if not 0.0 < fallback_fraction < 1.0:
        raise ValueError(
            "fallback_thinning_fraction must be strictly between 0 and 1."
        )
    if not 0.0 <= minimum_residual_fraction < 1.0:
        raise ValueError(
            "minimum_curve_residual_fraction must be in [0, 1)."
        )
    return fallback_fraction, minimum_residual_fraction


def _simulate_stand_policy(
    stand: pd.Series,
    policy: ManagementPolicy,
    lookup: pd.DataFrame,
    horizon: int,
    *,
    fallback_thinning_fraction: float,
    minimum_curve_residual_fraction: float,
) -> pd.DataFrame:
    initial_equation = _lookup_initial_equation(stand, lookup)
    post_thinning_equation = _validate_initial_growth_transition(
        stand,
        initial_equation,
        lookup,
    )

    age = int(stand["initial_age"])
    area_ha = float(stand["area_ha"])
    already_thinned = False
    force_initial_final_harvest = (
        str(stand["species"]) == PINUS
        and policy.thinning_age is not None
        and age > policy.thinning_age
    )

    # When the curve-difference method would leave an implausibly small
    # residual stock, Treemün applies a fixed-fraction thinning. The resulting
    # offset is carried forward so subsequent values follow the increments of
    # the post-thinning curve without dropping back to its near-zero level.
    post_thinning_continuity_adjustment_t = 0.0

    records: list[dict[str, object]] = []
    for period in range(1, horizon + 1):
        before_equation = (
            post_thinning_equation
            if already_thinned and post_thinning_equation is not None
            else initial_equation
        )
        unadjusted_curve_dry_wood_t = (
            before_equation.dry_wood_t_ha(age) * area_ha
        )
        before_dry_wood_t = max(
            unadjusted_curve_dry_wood_t
            + (
                post_thinning_continuity_adjustment_t
                if already_thinned and before_equation is post_thinning_equation
                else 0.0
            ),
            0.0,
        )

        operation = "none"
        harvested_dry_wood_t = 0.0
        after_equation = before_equation
        after_dry_wood_t = before_dry_wood_t

        thinning_calculation_method = "not_applicable"
        thinning_fallback_triggered = False
        candidate_post_thinning_dry_wood_t = np.nan
        candidate_curve_residual_fraction = np.nan
        candidate_thinning_fraction = np.nan
        applied_thinning_fraction = np.nan

        is_overdue_thinning_reset = (
            period == 1 and force_initial_final_harvest
        )
        is_scheduled_final_harvest = age == policy.final_harvest_age
        is_final_harvest = (
            is_overdue_thinning_reset or is_scheduled_final_harvest
        )
        is_thinning = (
            str(stand["species"]) == PINUS
            and policy.thinning_age is not None
            and age == policy.thinning_age
            and not already_thinned
            and not is_final_harvest
        )

        if is_final_harvest:
            operation = "final_harvest"
            harvested_dry_wood_t = before_dry_wood_t
            after_dry_wood_t = 0.0
            after_equation = initial_equation
        elif is_thinning:
            operation = "thinning"
            if post_thinning_equation is not None:
                candidate_post_thinning_dry_wood_t = max(
                    post_thinning_equation.dry_wood_t_ha(age) * area_ha,
                    0.0,
                )
                if before_dry_wood_t <= 0.0:
                    raise ValueError(
                        f"Stand {stand['stand_id']!r} has non-positive pre-thinning "
                        f"dry-wood stock at age {age}."
                    )

                candidate_curve_residual_fraction = (
                    candidate_post_thinning_dry_wood_t / before_dry_wood_t
                )
                candidate_thinning_fraction = (
                    before_dry_wood_t - candidate_post_thinning_dry_wood_t
                ) / before_dry_wood_t

                if candidate_post_thinning_dry_wood_t > before_dry_wood_t:
                    raise ValueError(
                        f"Post-thinning curve exceeds the pre-thinning stock for "
                        f"stand {stand['stand_id']!r} at age {age}: "
                        f"{candidate_post_thinning_dry_wood_t:.6f} > "
                        f"{before_dry_wood_t:.6f} tonnes."
                    )

                thinning_fallback_triggered = (
                    candidate_curve_residual_fraction
                    <= minimum_curve_residual_fraction
                )

                if thinning_fallback_triggered:
                    thinning_calculation_method = "fixed_fraction_fallback"
                    applied_thinning_fraction = fallback_thinning_fraction
                    harvested_dry_wood_t = (
                        applied_thinning_fraction * before_dry_wood_t
                    )
                    after_dry_wood_t = (
                        before_dry_wood_t - harvested_dry_wood_t
                    )
                    post_thinning_continuity_adjustment_t = (
                        after_dry_wood_t
                        - candidate_post_thinning_dry_wood_t
                    )
                else:
                    thinning_calculation_method = "curve_difference"
                    harvested_dry_wood_t = (
                        before_dry_wood_t
                        - candidate_post_thinning_dry_wood_t
                    )
                    after_dry_wood_t = candidate_post_thinning_dry_wood_t
                    applied_thinning_fraction = candidate_thinning_fraction
                    post_thinning_continuity_adjustment_t = 0.0

                after_equation = post_thinning_equation
            else:
                thinning_calculation_method = "fixed_fraction_no_post_curve"
                thinning_fallback_triggered = True
                applied_thinning_fraction = fallback_thinning_fraction
                harvested_dry_wood_t = (
                    applied_thinning_fraction * before_dry_wood_t
                )
                after_dry_wood_t = before_dry_wood_t - harvested_dry_wood_t
                post_thinning_continuity_adjustment_t = 0.0
            already_thinned = True

        managed_after_operation = already_thinned and not is_final_harvest
        records.append(
            {
                "period": period,
                "stand_id": str(stand["stand_id"]),
                "species": str(stand["species"]),
                "area_ha": area_ha,
                "policy": policy.name,
                "policy_number": policy.policy_number,
                "stand_age": age,
                "operation": operation,
                "final_harvest_reason": (
                    "overdue_thinning_rotation_reset"
                    if is_overdue_thinning_reset
                    else (
                        "scheduled_final_harvest"
                        if is_scheduled_final_harvest
                        else "not_applicable"
                    )
                ),
                "initial_rotation_reset_triggered": bool(
                    is_overdue_thinning_reset
                ),
                "management_state": (
                    "post_thinning" if managed_after_operation else "unthinned"
                ),
                "growth_curve_before_operation": before_equation.growth_curve,
                "growth_curve_after_operation": after_equation.growth_curve,
                "equation_id_before_operation": before_equation.equation_id,
                "equation_id_after_operation": after_equation.equation_id,
                "unadjusted_curve_dry_wood_t_before_operation": round(
                    unadjusted_curve_dry_wood_t, 3
                ),
                "post_thinning_continuity_adjustment_t": round(
                    post_thinning_continuity_adjustment_t, 3
                ),
                "standing_dry_wood_t_before_operation": round(before_dry_wood_t, 3),
                "harvested_dry_wood_t": round(harvested_dry_wood_t, 3),
                "standing_dry_wood_t_after_operation": round(after_dry_wood_t, 3),
                "thinning_calculation_method": thinning_calculation_method,
                "thinning_fallback_triggered": thinning_fallback_triggered,
                "candidate_post_thinning_dry_wood_t": (
                    round(float(candidate_post_thinning_dry_wood_t), 3)
                    if np.isfinite(candidate_post_thinning_dry_wood_t)
                    else np.nan
                ),
                "candidate_curve_residual_fraction": (
                    round(float(candidate_curve_residual_fraction), 6)
                    if np.isfinite(candidate_curve_residual_fraction)
                    else np.nan
                ),
                "candidate_thinning_fraction": (
                    round(float(candidate_thinning_fraction), 6)
                    if np.isfinite(candidate_thinning_fraction)
                    else np.nan
                ),
                "applied_thinning_fraction": (
                    round(float(applied_thinning_fraction), 6)
                    if np.isfinite(applied_thinning_fraction)
                    else np.nan
                ),
                "kitral_class": kitral_class(
                    str(stand["species"]), age, managed_after_operation
                ),
                "thinning_age": policy.thinning_age,
                "final_harvest_age": policy.final_harvest_age,
            }
        )

        if is_final_harvest:
            age = 1
            already_thinned = False
            post_thinning_continuity_adjustment_t = 0.0
        else:
            age += 1

    return pd.DataFrame.from_records(records)


def simulate_trajectories(
    stands: pd.DataFrame,
    lookup: pd.DataFrame,
    *,
    horizon: int,
    pinus_policies: Sequence[tuple[int, int]] = DEFAULT_PINUS_POLICIES,
    eucalyptus_policies: Sequence[tuple[int]] = DEFAULT_EUCALYPTUS_POLICIES,
    fallback_thinning_fraction: float = DEFAULT_FALLBACK_THINNING_FRACTION,
    minimum_curve_residual_fraction: float = (
        DEFAULT_MINIMUM_CURVE_RESIDUAL_FRACTION
    ),
) -> tuple[list[pd.DataFrame], list[dict[str, object]], dict, dict]:
    """Simulate every feasible stand-policy trajectory.

    Pinus stands must begin on a pre-thinning equation whose
    ``next_equation_id`` points to the post-thinning equation. If a policy's
    thinning age precedes the stand's initial biological age, the initial
    rotation is fully harvested in period 1 and period 2 starts at biological
    age 1 on the original pre-thinning equation.

    Returns
    -------
    forest:
        One annual trajectory DataFrame per feasible stand-policy alternative.
    policy_summary:
        Metadata for each trajectory.
    ending_dry_wood_by_policy:
        ``{(stand_id, policy): tonnes of dry wood after the final-period operation}``.
    harvested_dry_wood_by_period:
        ``{(period, species, policy, stand_id): harvested dry-wood tonnes}`` for
        positive harvests only.
    """
    if int(horizon) < 1:
        raise ValueError("horizon must be at least one year.")
    horizon = int(horizon)
    fallback_thinning_fraction, minimum_curve_residual_fraction = (
        _validate_thinning_transition_parameters(
            fallback_thinning_fraction,
            minimum_curve_residual_fraction,
        )
    )

    catalog = build_policy_catalog(pinus_policies, eucalyptus_policies)
    forest: list[pd.DataFrame] = []
    policy_summary: list[dict[str, object]] = []
    ending_dry_wood_by_policy: dict[tuple[str, str], float] = {}
    harvested_dry_wood_by_period: dict[tuple[int, str, str, str], float] = {}

    for _, stand in stands.iterrows():
        feasible_count = 0
        for policy in catalog[str(stand["species"])]:
            if not is_policy_feasible(
                str(stand["species"]), int(stand["initial_age"]), horizon, policy
            ):
                continue
            feasible_count += 1
            trajectory = _simulate_stand_policy(
                stand,
                policy,
                lookup,
                horizon,
                fallback_thinning_fraction=fallback_thinning_fraction,
                minimum_curve_residual_fraction=minimum_curve_residual_fraction,
            )
            forest.append(trajectory)
            ending_dry_wood_by_policy[(str(stand["stand_id"]), policy.name)] = float(
                trajectory.iloc[-1]["standing_dry_wood_t_after_operation"]
            )
            for row in trajectory.itertuples(index=False):
                if row.harvested_dry_wood_t > 0:
                    harvested_dry_wood_by_period[
                        (row.period, row.species, row.policy, row.stand_id)
                    ] = float(row.harvested_dry_wood_t)

            policy_summary.append(
                {
                    "stand_id": str(stand["stand_id"]),
                    "species": str(stand["species"]),
                    "area_ha": float(stand["area_ha"]),
                    "initial_age": int(stand["initial_age"]),
                    "ending_age": int(trajectory.iloc[-1]["stand_age"]),
                    "policy": policy.name,
                    "policy_number": policy.policy_number,
                    "thinning_age": policy.thinning_age,
                    "final_harvest_age": policy.final_harvest_age,
                    "initial_equation_id": int(
                        trajectory.iloc[0]["equation_id_before_operation"]
                    ),
                }
            )
        if feasible_count == 0:
            raise ValueError(
                f"Stand {stand['stand_id']!r} has no feasible policy for horizon={horizon}."
            )

    return (
        forest,
        policy_summary,
        ending_dry_wood_by_policy,
        harvested_dry_wood_by_period,
    )


def generate_random_stands(
    lookup: pd.DataFrame,
    *,
    number_of_stands: int,
    horizon: int,
    pinus_policies: Sequence[tuple[int, int]],
    eucalyptus_policies: Sequence[tuple[int]],
    random_seed: int,
) -> pd.DataFrame:
    """Generate a reproducible synthetic stand table from valid lookup strata."""
    if int(number_of_stands) < 1:
        raise ValueError("number_of_stands must be at least one.")
    rng = np.random.default_rng(int(random_seed))
    catalog = build_policy_catalog(pinus_policies, eucalyptus_policies)

    pinus_candidates = lookup.loc[
        lookup["species"].eq(PINUS)
        & lookup["growth_curve"].eq("pre_thinning_1250_700")
    ].copy()
    eucalyptus_candidates = lookup.loc[lookup["species"].eq(EUCALYPTUS)].copy()
    if pinus_candidates.empty or eucalyptus_candidates.empty:
        raise ValueError("Lookup table lacks valid initial equations for both species.")

    pinus_share = float(rng.uniform(0.4, 0.6))
    pinus_target = int(round(number_of_stands * pinus_share))
    species_sequence = [PINUS] * pinus_target + [EUCALYPTUS] * (
        number_of_stands - pinus_target
    )
    rng.shuffle(species_sequence)

    records: list[dict[str, object]] = []
    for index, species in enumerate(species_sequence, start=1):
        candidates = pinus_candidates if species == PINUS else eucalyptus_candidates
        age_range = range(1, 11) if species == PINUS else range(1, 21)
        valid_ages = [
            age
            for age in age_range
            if any(
                is_policy_feasible(species, age, int(horizon), policy)
                for policy in catalog[species]
            )
        ]
        if not valid_ages:
            raise ValueError(f"No feasible random initial ages for {species}.")
        row = candidates.iloc[int(rng.integers(0, len(candidates)))]
        records.append(
            {
                "stand_id": f"stand{index}",
                "area_ha": round(float(rng.uniform(1.0, 20.0)), 3),
                "species": species,
                "initial_age": int(rng.choice(valid_ages)),
                "zone": int(row["zone"]),
                "site_index": int(row["site_index"]),
                "management_regime": str(row["management_regime"]),
                "growth_curve": str(row["growth_curve"]),
                "initial_density_trees_ha": int(row["initial_density_trees_ha"]),
            }
        )
    return pd.DataFrame.from_records(records)

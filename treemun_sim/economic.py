"""Economic accounting for Treemün forest-management trajectories.

The module separates three user-facing economic interpretations:

``gross_revenue``
    Discounted gross income from harvested dry wood.
``net_unit_value``
    Discounted net margin when the user already supplies a net value per tonne.
``detailed_cash_flow``
    Net present value from explicit revenues and cost components.
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Mapping, Sequence

import pandas as pd

from .simulation import EUCALYPTUS, PINUS

VALID_ECONOMIC_MODES = {
    "gross_revenue",
    "net_unit_value",
    "detailed_cash_flow",
}

ECONOMIC_METRIC_BY_MODE = {
    "gross_revenue": "discounted_revenue",
    "net_unit_value": "discounted_net_margin",
    "detailed_cash_flow": "net_present_value",
}

SpeciesPeriodValue = (
    Real
    | Sequence[float]
    | Mapping[str, Real | Sequence[float]]
)


@dataclass(frozen=True)
class EconomicEvaluation:
    """Economic coefficients and transparent cash-flow components."""

    economic_mode: str
    economic_metric: str
    value_by_policy: dict[tuple[str, str], float]
    summary_by_policy: pd.DataFrame
    cash_flow_table: pd.DataFrame


def _normalise_mode(economic_mode: str) -> str:
    mode = str(economic_mode).strip().lower()
    aliases = {
        "revenue": "gross_revenue",
        "gross": "gross_revenue",
        "net_value": "net_unit_value",
        "margin": "net_unit_value",
        "npv": "detailed_cash_flow",
        "detailed": "detailed_cash_flow",
    }
    mode = aliases.get(mode, mode)
    if mode not in VALID_ECONOMIC_MODES:
        raise ValueError(
            f"economic_mode must be one of {sorted(VALID_ECONOMIC_MODES)}."
        )
    return mode


def _resolve_value(
    value: SpeciesPeriodValue,
    *,
    species: str,
    period: int,
    name: str,
) -> float:
    """Resolve a scalar, period sequence, or species-specific specification."""
    resolved = value
    if isinstance(resolved, Mapping):
        if species in resolved:
            resolved = resolved[species]
        elif "default" in resolved:
            resolved = resolved["default"]
        else:
            raise KeyError(
                f"{name} has no value for species {species!r} and no 'default'."
            )

    if isinstance(resolved, Real):
        return float(resolved)

    if isinstance(resolved, Sequence) and not isinstance(resolved, (str, bytes)):
        values = [float(item) for item in resolved]
        if not values:
            raise ValueError(f"{name} cannot be an empty sequence.")
        if int(period) < 1 or int(period) > len(values):
            raise ValueError(
                f"{name} provides {len(values)} period values but period {period} "
                "was requested."
            )
        return values[int(period) - 1]

    raise TypeError(
        f"{name} must be a number, a period sequence, or a species mapping."
    )


def _default_parameters() -> dict[str, object]:
    return {
        "revenue_per_dry_t": {PINUS: 9.0, EUCALYPTUS: 10.0},
        "net_value_per_dry_t": {PINUS: 9.0, EUCALYPTUS: 10.0},
        "variable_cost_per_dry_t": 0.0,
        "transport_cost_per_dry_t": 0.0,
        "thinning_cost_per_dry_t": 0.0,
        "final_harvest_cost_per_dry_t": 0.0,
        "thinning_cost_per_ha": 0.0,
        "final_harvest_cost_per_ha": 0.0,
        "replanting_cost_per_ha": 0.0,
        "annual_management_cost_per_ha": 0.0,
        "replanting_delay_periods": 0,
        "terminal_value_per_dry_t": 0.0,
    }


def _economic_parameters(parameters: Mapping[str, object] | None) -> dict[str, object]:
    result = _default_parameters()
    if parameters:
        unknown = set(parameters) - set(result)
        if unknown:
            raise ValueError(f"Unknown economic parameter(s): {sorted(unknown)}")
        result.update(dict(parameters))

    delay = int(result["replanting_delay_periods"])
    if delay < 0:
        raise ValueError("replanting_delay_periods must be non-negative.")
    result["replanting_delay_periods"] = delay
    return result


def _trajectory_identity(trajectory: pd.DataFrame) -> tuple[str, str, str, float]:
    required = {
        "period",
        "stand_id",
        "policy",
        "species",
        "area_ha",
        "operation",
        "harvested_dry_wood_t",
    }
    missing = required - set(trajectory.columns)
    if missing:
        raise ValueError(f"Trajectory is missing columns: {sorted(missing)}")
    if trajectory.empty:
        raise ValueError("Economic evaluation cannot use an empty trajectory.")

    stand_ids = trajectory["stand_id"].astype(str).unique()
    policies = trajectory["policy"].astype(str).unique()
    species_values = trajectory["species"].astype(str).unique()
    area_values = trajectory["area_ha"].astype(float).unique()
    if len(stand_ids) != 1 or len(policies) != 1 or len(species_values) != 1:
        raise ValueError("Each trajectory must describe one stand-policy alternative.")
    if len(area_values) != 1:
        raise ValueError("area_ha must be constant within a trajectory.")
    return stand_ids[0], policies[0], species_values[0], float(area_values[0])


def evaluate_forest_economics(
    forest: Sequence[pd.DataFrame],
    *,
    economic_mode: str = "net_unit_value",
    discount_rate: float = 0.08,
    economic_parameters: Mapping[str, object] | None = None,
) -> EconomicEvaluation:
    """Evaluate every simulated stand-policy trajectory economically.

    Parameters are intentionally explicit and may be scalars, period sequences,
    or mappings by species. Costs per hectare use the stand area. Replanting is
    triggered by a final harvest and can be delayed by a configurable number of
    periods. In ``detailed_cash_flow`` mode, ``terminal_value_per_dry_t`` adds
    the discounted residual value of dry wood remaining at the horizon.
    """
    mode = _normalise_mode(economic_mode)
    metric = ECONOMIC_METRIC_BY_MODE[mode]
    rate = float(discount_rate)
    if rate < 0.0:
        raise ValueError("discount_rate must be non-negative.")
    parameters = _economic_parameters(economic_parameters)

    rows: list[dict[str, object]] = []
    for trajectory in forest:
        stand_id, policy, species, area_ha = _trajectory_identity(trajectory)
        for row in trajectory.sort_values("period").itertuples(index=False):
            period = int(row.period)
            operation = str(row.operation)
            harvested = float(row.harvested_dry_wood_t)

            revenue_per_t = _resolve_value(
                parameters["revenue_per_dry_t"],
                species=species,
                period=period,
                name="revenue_per_dry_t",
            )
            net_value_per_t = _resolve_value(
                parameters["net_value_per_dry_t"],
                species=species,
                period=period,
                name="net_value_per_dry_t",
            )

            gross_revenue = 0.0
            net_unit_margin = 0.0
            variable_cost = 0.0
            transport_cost = 0.0
            operation_cost_per_t = 0.0
            operation_cost_per_ha = 0.0
            replanting_cost = 0.0
            annual_management_cost = 0.0
            terminal_value = 0.0

            if mode == "gross_revenue":
                gross_revenue = harvested * revenue_per_t
                net_cash_flow = gross_revenue
            elif mode == "net_unit_value":
                net_unit_margin = harvested * net_value_per_t
                net_cash_flow = net_unit_margin
            else:
                gross_revenue = harvested * revenue_per_t
                variable_cost = harvested * _resolve_value(
                    parameters["variable_cost_per_dry_t"],
                    species=species,
                    period=period,
                    name="variable_cost_per_dry_t",
                )
                transport_cost = harvested * _resolve_value(
                    parameters["transport_cost_per_dry_t"],
                    species=species,
                    period=period,
                    name="transport_cost_per_dry_t",
                )
                if operation == "thinning":
                    operation_cost_per_t = harvested * _resolve_value(
                        parameters["thinning_cost_per_dry_t"],
                        species=species,
                        period=period,
                        name="thinning_cost_per_dry_t",
                    )
                    operation_cost_per_ha = area_ha * _resolve_value(
                        parameters["thinning_cost_per_ha"],
                        species=species,
                        period=period,
                        name="thinning_cost_per_ha",
                    )
                elif operation == "final_harvest":
                    operation_cost_per_t = harvested * _resolve_value(
                        parameters["final_harvest_cost_per_dry_t"],
                        species=species,
                        period=period,
                        name="final_harvest_cost_per_dry_t",
                    )
                    operation_cost_per_ha = area_ha * _resolve_value(
                        parameters["final_harvest_cost_per_ha"],
                        species=species,
                        period=period,
                        name="final_harvest_cost_per_ha",
                    )
                annual_management_cost = area_ha * _resolve_value(
                    parameters["annual_management_cost_per_ha"],
                    species=species,
                    period=period,
                    name="annual_management_cost_per_ha",
                )
                if operation == "final_harvest" and int(
                    parameters["replanting_delay_periods"]
                ) == 0:
                    replanting_cost = area_ha * _resolve_value(
                        parameters["replanting_cost_per_ha"],
                        species=species,
                        period=period,
                        name="replanting_cost_per_ha",
                    )
                net_cash_flow = (
                    gross_revenue
                    - variable_cost
                    - transport_cost
                    - operation_cost_per_t
                    - operation_cost_per_ha
                    - replanting_cost
                    - annual_management_cost
                )

            discount_factor = (1.0 + rate) ** period
            rows.append(
                {
                    "period": period,
                    "stand_id": stand_id,
                    "policy": policy,
                    "species": species,
                    "area_ha": area_ha,
                    "economic_mode": mode,
                    "economic_metric": metric,
                    "economic_event": operation,
                    "operation": operation,
                    "harvested_dry_wood_t": harvested,
                    "unit_economic_value_per_t": (
                        revenue_per_t if mode != "net_unit_value" else net_value_per_t
                    ),
                    "gross_revenue": gross_revenue,
                    "net_unit_margin": net_unit_margin,
                    "variable_cost": variable_cost,
                    "transport_cost": transport_cost,
                    "operation_cost_per_t_component": operation_cost_per_t,
                    "operation_cost_per_ha_component": operation_cost_per_ha,
                    "replanting_cost": replanting_cost,
                    "annual_management_cost": annual_management_cost,
                    "terminal_value": terminal_value,
                    "net_cash_flow": net_cash_flow,
                    "discount_factor": discount_factor,
                    "discounted_gross_revenue": gross_revenue / discount_factor,
                    "discounted_net_unit_margin": net_unit_margin / discount_factor,
                    "discounted_variable_cost": variable_cost / discount_factor,
                    "discounted_transport_cost": transport_cost / discount_factor,
                    "discounted_operation_cost_per_t_component": operation_cost_per_t / discount_factor,
                    "discounted_operation_cost_per_ha_component": operation_cost_per_ha / discount_factor,
                    "discounted_replanting_cost": replanting_cost / discount_factor,
                    "discounted_annual_management_cost": annual_management_cost / discount_factor,
                    "discounted_terminal_value": terminal_value / discount_factor,
                    "discounted_economic_value": net_cash_flow / discount_factor,
                }
            )

            delay = int(parameters["replanting_delay_periods"])
            if (
                mode == "detailed_cash_flow"
                and operation == "final_harvest"
                and delay > 0
            ):
                cost_period = period + delay
                delayed_replanting_cost = area_ha * _resolve_value(
                    parameters["replanting_cost_per_ha"],
                    species=species,
                    period=period,
                    name="replanting_cost_per_ha",
                )
                delayed_discount_factor = (1.0 + rate) ** cost_period
                rows.append(
                    {
                        "period": cost_period,
                        "stand_id": stand_id,
                        "policy": policy,
                        "species": species,
                        "area_ha": area_ha,
                        "economic_mode": mode,
                        "economic_metric": metric,
                        "economic_event": "replanting",
                        "operation": "replanting",
                        "harvested_dry_wood_t": 0.0,
                        "unit_economic_value_per_t": 0.0,
                        "gross_revenue": 0.0,
                        "net_unit_margin": 0.0,
                        "variable_cost": 0.0,
                        "transport_cost": 0.0,
                        "operation_cost_per_t_component": 0.0,
                        "operation_cost_per_ha_component": 0.0,
                        "replanting_cost": delayed_replanting_cost,
                        "annual_management_cost": 0.0,
                        "terminal_value": 0.0,
                        "net_cash_flow": -delayed_replanting_cost,
                        "discount_factor": delayed_discount_factor,
                        "discounted_gross_revenue": 0.0,
                        "discounted_net_unit_margin": 0.0,
                        "discounted_variable_cost": 0.0,
                        "discounted_transport_cost": 0.0,
                        "discounted_operation_cost_per_t_component": 0.0,
                        "discounted_operation_cost_per_ha_component": 0.0,
                        "discounted_replanting_cost": delayed_replanting_cost / delayed_discount_factor,
                        "discounted_annual_management_cost": 0.0,
                        "discounted_terminal_value": 0.0,
                        "discounted_economic_value": (
                            -delayed_replanting_cost / delayed_discount_factor
                        ),
                    }
                )

        if mode == "detailed_cash_flow":
            final_row = trajectory.sort_values("period").iloc[-1]
            terminal_period = int(final_row["period"])
            terminal_value_per_t = _resolve_value(
                parameters["terminal_value_per_dry_t"],
                species=species,
                period=terminal_period,
                name="terminal_value_per_dry_t",
            )
            if abs(terminal_value_per_t) > 0.0:
                if "standing_dry_wood_t_after_operation" not in trajectory.columns:
                    raise ValueError(
                        "standing_dry_wood_t_after_operation is required when "
                        "terminal_value_per_dry_t is non-zero."
                    )
                ending_dry_wood_t = float(
                    final_row["standing_dry_wood_t_after_operation"]
                )
            else:
                ending_dry_wood_t = 0.0
            terminal_value = ending_dry_wood_t * terminal_value_per_t
            if abs(terminal_value) > 0.0:
                terminal_discount_factor = (1.0 + rate) ** terminal_period
                rows.append(
                    {
                        "period": terminal_period,
                        "stand_id": stand_id,
                        "policy": policy,
                        "species": species,
                        "area_ha": area_ha,
                        "economic_mode": mode,
                        "economic_metric": metric,
                        "economic_event": "terminal_value",
                        "operation": "terminal_value",
                        "harvested_dry_wood_t": 0.0,
                        "unit_economic_value_per_t": terminal_value_per_t,
                        "gross_revenue": 0.0,
                        "net_unit_margin": 0.0,
                        "variable_cost": 0.0,
                        "transport_cost": 0.0,
                        "operation_cost_per_t_component": 0.0,
                        "operation_cost_per_ha_component": 0.0,
                        "replanting_cost": 0.0,
                        "annual_management_cost": 0.0,
                        "terminal_value": terminal_value,
                        "net_cash_flow": terminal_value,
                        "discount_factor": terminal_discount_factor,
                        "discounted_gross_revenue": 0.0,
                        "discounted_net_unit_margin": 0.0,
                        "discounted_variable_cost": 0.0,
                        "discounted_transport_cost": 0.0,
                        "discounted_operation_cost_per_t_component": 0.0,
                        "discounted_operation_cost_per_ha_component": 0.0,
                        "discounted_replanting_cost": 0.0,
                        "discounted_annual_management_cost": 0.0,
                        "discounted_terminal_value": (
                            terminal_value / terminal_discount_factor
                        ),
                        "discounted_economic_value": (
                            terminal_value / terminal_discount_factor
                        ),
                    }
                )

    cash_flow_table = pd.DataFrame(rows)
    if cash_flow_table.empty:
        raise ValueError("forest must contain at least one non-empty trajectory.")

    cost_columns = [
        "variable_cost",
        "transport_cost",
        "operation_cost_per_t_component",
        "operation_cost_per_ha_component",
        "replanting_cost",
        "annual_management_cost",
    ]
    group_columns = ["stand_id", "policy", "species", "economic_mode", "economic_metric"]
    summary = (
        cash_flow_table.groupby(group_columns, as_index=False)
        .agg(
            gross_revenue=("gross_revenue", "sum"),
            net_unit_margin=("net_unit_margin", "sum"),
            variable_cost=("variable_cost", "sum"),
            transport_cost=("transport_cost", "sum"),
            operation_cost_per_t_component=("operation_cost_per_t_component", "sum"),
            operation_cost_per_ha_component=("operation_cost_per_ha_component", "sum"),
            replanting_cost=("replanting_cost", "sum"),
            annual_management_cost=("annual_management_cost", "sum"),
            terminal_value=("terminal_value", "sum"),
            undiscounted_net_cash_flow=("net_cash_flow", "sum"),
            discounted_gross_revenue=("discounted_gross_revenue", "sum"),
            discounted_net_unit_margin=("discounted_net_unit_margin", "sum"),
            discounted_variable_cost=("discounted_variable_cost", "sum"),
            discounted_transport_cost=("discounted_transport_cost", "sum"),
            discounted_operation_cost_per_t_component=("discounted_operation_cost_per_t_component", "sum"),
            discounted_operation_cost_per_ha_component=("discounted_operation_cost_per_ha_component", "sum"),
            discounted_replanting_cost=("discounted_replanting_cost", "sum"),
            discounted_annual_management_cost=("discounted_annual_management_cost", "sum"),
            discounted_terminal_value=("discounted_terminal_value", "sum"),
            economic_value=("discounted_economic_value", "sum"),
        )
    )
    summary["total_cost"] = summary[cost_columns].sum(axis=1)
    summary["total_income"] = (
        summary["gross_revenue"] + summary["terminal_value"]
    )
    summary["discounted_total_cost"] = summary[
        [
            "discounted_variable_cost",
            "discounted_transport_cost",
            "discounted_operation_cost_per_t_component",
            "discounted_operation_cost_per_ha_component",
            "discounted_replanting_cost",
            "discounted_annual_management_cost",
        ]
    ].sum(axis=1)
    summary["discounted_total_income"] = (
        summary["discounted_gross_revenue"]
        + summary["discounted_terminal_value"]
    )
    value_by_policy = {
        (str(row.stand_id), str(row.policy)): float(row.economic_value)
        for row in summary.itertuples(index=False)
    }
    return EconomicEvaluation(
        economic_mode=mode,
        economic_metric=metric,
        value_by_policy=value_by_policy,
        summary_by_policy=summary,
        cash_flow_table=cash_flow_table.sort_values(
            ["stand_id", "policy", "period", "economic_event"]
        ).reset_index(drop=True),
    )


__all__ = [
    "ECONOMIC_METRIC_BY_MODE",
    "EconomicEvaluation",
    "VALID_ECONOMIC_MODES",
    "evaluate_forest_economics",
]

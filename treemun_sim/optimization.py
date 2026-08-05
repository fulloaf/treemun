"""Mixed-integer harvest-scheduling models for Treemün 2.0."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Iterable, Mapping, Sequence

import pandas as pd

from .economic import ECONOMIC_METRIC_BY_MODE, VALID_ECONOMIC_MODES, evaluate_forest_economics
from .simulation import EUCALYPTUS, PINUS

VALID_OBJECTIVES = {"economic", "npv", "carbon", "weighted"}
VALID_EVEN_FLOW_MODES = {
    "none",
    "two_sided_average",
    "two_sided_consecutive",
    "nondecreasing",
}


def _require_pyomo():
    try:
        import pyomo.environ as pyo
        from pyomo.opt import SolverFactory
    except ImportError as exc:
        raise ImportError(
            "Optimization requires Pyomo. Install it with "
            "`pip install treemun-sim[optimization]`."
        ) from exc
    return pyo, SolverFactory


def _period_values(value: float | Sequence[float], horizon: int, name: str) -> dict[int, float]:
    if isinstance(value, (int, float)):
        return {period: float(value) for period in range(1, horizon + 1)}
    values = [float(item) for item in value]
    if len(values) != horizon:
        raise ValueError(f"{name} must contain {horizon} values; found {len(values)}.")
    return {period: values[period - 1] for period in range(1, horizon + 1)}


def _validate_weights(npv_weight: float, carbon_weight: float) -> tuple[float, float]:
    npv_weight = float(npv_weight)
    carbon_weight = float(carbon_weight)
    if npv_weight < 0 or carbon_weight < 0:
        raise ValueError("npv_weight and carbon_weight must be non-negative.")
    if npv_weight + carbon_weight <= 0:
        raise ValueError("At least one objective weight must be positive.")
    return npv_weight, carbon_weight


def _policy_metadata(policy_summary: Sequence[Mapping[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame(policy_summary)
    required = {"stand_id", "species", "policy"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"policy_summary is missing columns: {sorted(missing)}")
    frame = frame.drop_duplicates(["stand_id", "policy"]).copy()
    if frame.duplicated(["stand_id", "policy"]).any():
        raise ValueError("Each stand-policy alternative must be unique.")
    return frame


def _initial_dry_wood_by_stand(
    forest: Sequence[pd.DataFrame],
) -> dict[str, float]:
    """Return period-one pre-operation stock for every stand.

    The value must be policy-invariant within each stand. This provides a
    transparent baseline for terminal stock fractions.
    """
    values: dict[str, float] = {}
    for trajectory in forest:
        required = {
            "stand_id",
            "period",
            "standing_dry_wood_t_before_operation",
        }
        missing = required - set(trajectory.columns)
        if missing:
            raise ValueError(
                f"Trajectory is missing columns required for the initial stock: "
                f"{sorted(missing)}"
            )
        first = trajectory.sort_values("period").iloc[0]
        stand_id = str(first["stand_id"])
        value = float(first["standing_dry_wood_t_before_operation"])
        if stand_id in values and abs(values[stand_id] - value) > max(
            1e-6, 1e-9 * max(abs(values[stand_id]), abs(value), 1.0)
        ):
            raise ValueError(
                f"Initial dry-wood stock is not policy-invariant for stand "
                f"{stand_id!r}."
            )
        values[stand_id] = value
    if not values:
        raise ValueError("forest must contain at least one trajectory.")
    return values


def build_forest_management_model(
    *,
    policy_summary: Sequence[Mapping[str, object]],
    ending_dry_wood_by_policy: Mapping[tuple[str, str], float],
    harvested_dry_wood_by_period: Mapping[tuple[int, str, str, str], float],
    horizon: int,
    forest: Sequence[pd.DataFrame] | None = None,
    carbon_stock_time_by_period: Mapping[tuple[int, str, str, str], float] | None = None,
    economic_mode: str = "net_unit_value",
    economic_parameters: Mapping[str, object] | None = None,
    economic_value_by_policy: Mapping[tuple[str, str], float] | None = None,
    pine_revenue_per_t: float | Sequence[float] | None = None,
    eucalyptus_revenue_per_t: float | Sequence[float] | None = None,
    discount_rate: float = 0.08,
    minimum_ending_dry_wood_t: float = 0.0,
    minimum_ending_dry_wood_fraction: float | None = None,
    minimum_ending_carbon_tC: float | None = None,
    ending_carbon_by_policy: Mapping[tuple[str, str], float] | None = None,
    even_flow_mode: str = "two_sided_average",
    even_flow_tolerance: float = 0.10,
    objective: str = "npv",
    npv_weight: float = 0.5,
    carbon_weight: float = 0.5,
    npv_scale: float | None = None,
    carbon_scale: float | None = None,
    npv_reference: float | None = None,
    carbon_reference: float | None = None,
):
    """Build the Treemün binary stand-policy selection model.

    The economic criterion can represent discounted gross revenue, discounted
    net unit margin, or detailed net present value. The carbon objective uses
    cumulative post-operation standing-wood carbon stock-time in tC·year.
    """
    build_started = perf_counter()
    pyo, _ = _require_pyomo()
    horizon = int(horizon)
    if horizon < 1:
        raise ValueError("horizon must be at least one.")
    if not 0 <= float(discount_rate):
        raise ValueError("discount_rate must be non-negative.")
    if not 0 <= float(even_flow_tolerance) <= 1:
        raise ValueError("even_flow_tolerance must be between zero and one.")
    objective = str(objective).strip().lower()
    if objective not in VALID_OBJECTIVES:
        raise ValueError(f"objective must be one of {sorted(VALID_OBJECTIVES)}.")
    if objective == "npv":
        # Backward-compatible alias. The economic metric is determined by
        # economic_mode and is only a true NPV in detailed_cash_flow mode.
        objective = "economic"
    economic_mode = str(economic_mode).strip().lower()
    if economic_mode not in VALID_ECONOMIC_MODES:
        raise ValueError(
            f"economic_mode must be one of {sorted(VALID_ECONOMIC_MODES)}."
        )
    even_flow_mode = str(even_flow_mode).strip().lower()
    if even_flow_mode not in VALID_EVEN_FLOW_MODES:
        raise ValueError(
            f"even_flow_mode must be one of {sorted(VALID_EVEN_FLOW_MODES)}."
        )
    if objective in {"carbon", "weighted"} and carbon_stock_time_by_period is None:
        raise ValueError(
            "carbon_stock_time_by_period is required for carbon or weighted objectives."
        )
    if minimum_ending_carbon_tC is not None and ending_carbon_by_policy is None:
        raise ValueError(
            "ending_carbon_by_policy is required when minimum_ending_carbon_tC is set."
        )
    initial_dry_wood_by_stand: dict[str, float] = {}
    initial_dry_wood_total_t: float | None = None
    if minimum_ending_dry_wood_fraction is not None:
        minimum_ending_dry_wood_fraction = float(
            minimum_ending_dry_wood_fraction
        )
        if not 0.0 <= minimum_ending_dry_wood_fraction <= 1.0:
            raise ValueError(
                "minimum_ending_dry_wood_fraction must be between zero and one."
            )
        if forest is None:
            raise ValueError(
                "forest is required when minimum_ending_dry_wood_fraction is set."
            )
        initial_dry_wood_by_stand = _initial_dry_wood_by_stand(forest)
        initial_dry_wood_total_t = float(
            sum(initial_dry_wood_by_stand.values())
        )
    npv_weight, carbon_weight = _validate_weights(npv_weight, carbon_weight)

    metadata = _policy_metadata(policy_summary)
    alternatives = [
        (str(row.stand_id), str(row.policy))
        for row in metadata.itertuples(index=False)
    ]
    stands = sorted(metadata["stand_id"].astype(str).unique())
    species_by_alternative = {
        (str(row.stand_id), str(row.policy)): str(row.species)
        for row in metadata.itertuples(index=False)
    }
    alternatives_by_stand = {
        stand_id: [alternative for alternative in alternatives if alternative[0] == stand_id]
        for stand_id in stands
    }

    harvest_coefficients: dict[tuple[int, str, str], float] = {}
    carbon_coefficients = {alternative: 0.0 for alternative in alternatives}
    for period in range(1, horizon + 1):
        for stand_id, policy in alternatives:
            species = species_by_alternative[(stand_id, policy)]
            harvested = float(
                harvested_dry_wood_by_period.get(
                    (period, species, policy, stand_id), 0.0
                )
            )
            harvest_coefficients[(period, stand_id, policy)] = harvested
            if carbon_stock_time_by_period is not None:
                carbon_coefficients[(stand_id, policy)] += float(
                    carbon_stock_time_by_period.get(
                        (period, species, policy, stand_id), 0.0
                    )
                )

    economic_evaluation = None
    if economic_value_by_policy is not None:
        economic_coefficients = {
            alternative: float(economic_value_by_policy.get(alternative, 0.0))
            for alternative in alternatives
        }
    elif forest is not None:
        parameters = dict(economic_parameters or {})
        if pine_revenue_per_t is not None or eucalyptus_revenue_per_t is not None:
            parameter_name = (
                "net_value_per_dry_t"
                if economic_mode == "net_unit_value"
                else "revenue_per_dry_t"
            )
            existing_species_values = parameters.get(parameter_name, {})
            if not isinstance(existing_species_values, Mapping):
                raise ValueError(
                    f"{parameter_name} must be a species mapping when legacy "
                    "pine/eucalyptus arguments are supplied."
                )
            species_values = dict(existing_species_values)
            if pine_revenue_per_t is not None:
                species_values[PINUS] = pine_revenue_per_t
            if eucalyptus_revenue_per_t is not None:
                species_values[EUCALYPTUS] = eucalyptus_revenue_per_t
            parameters[parameter_name] = species_values
        economic_evaluation = evaluate_forest_economics(
            forest,
            economic_mode=economic_mode,
            discount_rate=discount_rate,
            economic_parameters=parameters,
        )
        economic_coefficients = {
            alternative: float(
                economic_evaluation.value_by_policy.get(alternative, 0.0)
            )
            for alternative in alternatives
        }
    else:
        if economic_mode == "detailed_cash_flow":
            raise ValueError(
                "forest is required for detailed_cash_flow because operation- "
                "and area-based costs must be evaluated from annual trajectories."
            )
        parameter_name = (
            "net_value_per_dry_t"
            if economic_mode == "net_unit_value"
            else "revenue_per_dry_t"
        )
        parameters = dict(economic_parameters or {})
        default_values = {PINUS: 9.0, EUCALYPTUS: 10.0}
        configured_values = parameters.get(parameter_name, default_values)
        if pine_revenue_per_t is not None or eucalyptus_revenue_per_t is not None:
            configured_values = dict(
                configured_values
                if isinstance(configured_values, Mapping)
                else default_values
            )
            if pine_revenue_per_t is not None:
                configured_values[PINUS] = pine_revenue_per_t
            if eucalyptus_revenue_per_t is not None:
                configured_values[EUCALYPTUS] = eucalyptus_revenue_per_t
        pine_value = _period_values(
            configured_values.get(PINUS, default_values[PINUS])
            if isinstance(configured_values, Mapping)
            else configured_values,
            horizon,
            f"{parameter_name}[{PINUS}]",
        )
        eucalyptus_value = _period_values(
            configured_values.get(EUCALYPTUS, default_values[EUCALYPTUS])
            if isinstance(configured_values, Mapping)
            else configured_values,
            horizon,
            f"{parameter_name}[{EUCALYPTUS}]",
        )
        economic_coefficients = {alternative: 0.0 for alternative in alternatives}
        for period in range(1, horizon + 1):
            for stand_id, policy in alternatives:
                species = species_by_alternative[(stand_id, policy)]
                harvested = harvest_coefficients[(period, stand_id, policy)]
                unit_value = (
                    pine_value[period]
                    if species == PINUS
                    else eucalyptus_value[period]
                )
                economic_coefficients[(stand_id, policy)] += (
                    harvested
                    * unit_value
                    / (1.0 + float(discount_rate)) ** period
                )

    economic_metric = ECONOMIC_METRIC_BY_MODE[economic_mode]
    # ``npv_coefficients`` is retained internally as a compatibility alias for
    # the original 2.0 API and for existing normalization helpers.
    npv_coefficients = economic_coefficients

    npv_assignment_lower = sum(
        min(npv_coefficients[alternative] for alternative in alternatives_by_stand[stand_id])
        for stand_id in stands
    )
    npv_assignment_upper = sum(
        max(npv_coefficients[alternative] for alternative in alternatives_by_stand[stand_id])
        for stand_id in stands
    )
    carbon_assignment_lower = sum(
        min(carbon_coefficients[alternative] for alternative in alternatives_by_stand[stand_id])
        for stand_id in stands
    )
    carbon_assignment_upper = sum(
        max(carbon_coefficients[alternative] for alternative in alternatives_by_stand[stand_id])
        for stand_id in stands
    )

    if npv_reference is None:
        npv_reference = npv_assignment_lower
    if carbon_reference is None:
        carbon_reference = carbon_assignment_lower
    if npv_scale is None:
        npv_scale = max(npv_assignment_upper - npv_assignment_lower, 1.0)
    if carbon_scale is None:
        carbon_scale = max(
            carbon_assignment_upper - carbon_assignment_lower, 1.0
        )
    if float(npv_scale) <= 0 or float(carbon_scale) <= 0:
        raise ValueError("npv_scale and carbon_scale must be positive.")

    model = pyo.ConcreteModel(name="TreemunForestManagement")
    model.STANDS = pyo.Set(initialize=stands, ordered=True)
    model.ALTERNATIVES = pyo.Set(dimen=2, initialize=alternatives, ordered=True)
    model.PERIODS = pyo.RangeSet(1, horizon)
    model.select_policy = pyo.Var(model.ALTERNATIVES, domain=pyo.Binary)
    model.harvested_dry_wood_t = pyo.Var(model.PERIODS, domain=pyo.NonNegativeReals)

    model.economic_value = pyo.Expression(
        expr=sum(
            economic_coefficients[alternative] * model.select_policy[alternative]
            for alternative in alternatives
        )
    )
    # Compatibility alias: in gross_revenue and net_unit_value modes this is
    # not a true NPV. New code should use ``economic_value`` and inspect
    # ``economic_metric`` in the extracted solution.
    model.npv_value = pyo.Expression(expr=model.economic_value)
    model.carbon_stock_time_value = pyo.Expression(
        expr=sum(
            carbon_coefficients[alternative] * model.select_policy[alternative]
            for alternative in alternatives
        )
    )
    model.ending_dry_wood_t = pyo.Expression(
        expr=sum(
            float(ending_dry_wood_by_policy.get(alternative, 0.0))
            * model.select_policy[alternative]
            for alternative in alternatives
        )
    )

    if ending_carbon_by_policy is not None:
        model.ending_carbon_tC = pyo.Expression(
            expr=sum(
                float(ending_carbon_by_policy.get(alternative, 0.0))
                * model.select_policy[alternative]
                for alternative in alternatives
            )
        )

    def assignment_rule(pyomo_model, stand_id):
        return sum(
            pyomo_model.select_policy[alternative]
            for alternative in alternatives_by_stand[str(stand_id)]
        ) == 1

    model.single_policy_per_stand = pyo.Constraint(model.STANDS, rule=assignment_rule)

    def harvest_tracking_rule(pyomo_model, period):
        return pyomo_model.harvested_dry_wood_t[period] == sum(
            harvest_coefficients[(int(period), stand_id, policy)]
            * pyomo_model.select_policy[stand_id, policy]
            for stand_id, policy in alternatives
        )

    model.harvest_tracking = pyo.Constraint(model.PERIODS, rule=harvest_tracking_rule)

    if even_flow_mode == "two_sided_average":
        model.average_annual_harvest_t = pyo.Expression(
            expr=sum(model.harvested_dry_wood_t[period] for period in model.PERIODS)
            / horizon
        )

        def even_flow_lower_rule(pyomo_model, period):
            return pyomo_model.harvested_dry_wood_t[period] >= (
                1.0 - float(even_flow_tolerance)
            ) * pyomo_model.average_annual_harvest_t

        def even_flow_upper_rule(pyomo_model, period):
            return pyomo_model.harvested_dry_wood_t[period] <= (
                1.0 + float(even_flow_tolerance)
            ) * pyomo_model.average_annual_harvest_t

        model.even_flow_lower = pyo.Constraint(model.PERIODS, rule=even_flow_lower_rule)
        model.even_flow_upper = pyo.Constraint(model.PERIODS, rule=even_flow_upper_rule)

    elif even_flow_mode == "two_sided_consecutive":
        def consecutive_lower_rule(pyomo_model, period):
            if int(period) == horizon:
                return pyo.Constraint.Skip
            return pyomo_model.harvested_dry_wood_t[period + 1] >= (
                1.0 - float(even_flow_tolerance)
            ) * pyomo_model.harvested_dry_wood_t[period]

        def consecutive_upper_rule(pyomo_model, period):
            if int(period) == horizon:
                return pyo.Constraint.Skip
            return pyomo_model.harvested_dry_wood_t[period + 1] <= (
                1.0 + float(even_flow_tolerance)
            ) * pyomo_model.harvested_dry_wood_t[period]

        model.even_flow_lower = pyo.Constraint(model.PERIODS, rule=consecutive_lower_rule)
        model.even_flow_upper = pyo.Constraint(model.PERIODS, rule=consecutive_upper_rule)

    elif even_flow_mode == "nondecreasing":
        def nondecreasing_rule(pyomo_model, period):
            if int(period) == horizon:
                return pyo.Constraint.Skip
            return pyomo_model.harvested_dry_wood_t[period + 1] >= (
                1.0 - float(even_flow_tolerance)
            ) * pyomo_model.harvested_dry_wood_t[period]

        model.even_flow = pyo.Constraint(model.PERIODS, rule=nondecreasing_rule)

    model.minimum_ending_dry_wood = pyo.Constraint(
        expr=model.ending_dry_wood_t >= float(minimum_ending_dry_wood_t)
    )
    if minimum_ending_dry_wood_fraction is not None:
        model.minimum_ending_dry_wood_fraction = pyo.Constraint(
            expr=model.ending_dry_wood_t
            >= float(minimum_ending_dry_wood_fraction)
            * float(initial_dry_wood_total_t)
        )
    if minimum_ending_carbon_tC is not None:
        model.minimum_ending_carbon = pyo.Constraint(
            expr=model.ending_carbon_tC >= float(minimum_ending_carbon_tC)
        )

    if objective == "economic":
        objective_expression = model.economic_value
    elif objective == "carbon":
        objective_expression = model.carbon_stock_time_value
    else:
        objective_expression = (
            npv_weight
            * (model.economic_value - float(npv_reference))
            / float(npv_scale)
            + carbon_weight
            * (model.carbon_stock_time_value - float(carbon_reference))
            / float(carbon_scale)
        )
    model.objective = pyo.Objective(expr=objective_expression, sense=pyo.maximize)

    model._treemun_metadata = {
        "objective": objective,
        "horizon": horizon,
        "alternatives": alternatives,
        "alternatives_by_stand": alternatives_by_stand,
        "species_by_alternative": species_by_alternative,
        "harvest_coefficients": harvest_coefficients,
        "economic_mode": economic_mode,
        "economic_metric": economic_metric,
        "economic_coefficients": economic_coefficients,
        "npv_coefficients": npv_coefficients,
        "economic_summary_by_policy": (
            economic_evaluation.summary_by_policy.copy()
            if economic_evaluation is not None
            else None
        ),
        "economic_cash_flow_table": (
            economic_evaluation.cash_flow_table.copy()
            if economic_evaluation is not None
            else None
        ),
        "carbon_coefficients": carbon_coefficients,
        "ending_dry_wood_by_policy": dict(ending_dry_wood_by_policy),
        "ending_carbon_by_policy": dict(ending_carbon_by_policy or {}),
        "policy_summary": metadata.to_dict("records"),
        "npv_scale": float(npv_scale),
        "carbon_scale": float(carbon_scale),
        "npv_reference": float(npv_reference),
        "carbon_reference": float(carbon_reference),
        "normalization_bounds": {
            "npv_lower": float(npv_assignment_lower),
            "npv_upper": float(npv_assignment_upper),
            "carbon_lower": float(carbon_assignment_lower),
            "carbon_upper": float(carbon_assignment_upper),
        },
        "npv_weight": npv_weight,
        "carbon_weight": carbon_weight,
        "even_flow_mode": even_flow_mode,
        "even_flow_tolerance": float(even_flow_tolerance),
        "minimum_ending_dry_wood_t": float(minimum_ending_dry_wood_t),
        "minimum_ending_dry_wood_fraction": minimum_ending_dry_wood_fraction,
        "initial_dry_wood_by_stand": initial_dry_wood_by_stand,
        "initial_dry_wood_total_t": initial_dry_wood_total_t,
        "model_build_time_seconds": float(perf_counter() - build_started),
        "spatial_extension_build_time_seconds": 0.0,
    }
    model._treemun_solve_history = []
    return model


# Backward-friendly English alias retained because the 2.0 draft documentation used it.
forest_management_optimization_model = build_forest_management_model


def _set_solver_option(solver, key: str, value: object) -> None:
    """Set one native solver option on a Pyomo solver interface."""
    options = getattr(solver, "options", None)
    if options is not None:
        options[key] = value
        return

    for attribute in ("highs_options", "cplex_options", "gurobi_options"):
        native_options = getattr(solver, attribute, None)
        if native_options is not None:
            native_options[key] = value
            return

    raise RuntimeError(
        f"The selected solver interface does not expose an option container "
        f"for {key!r}."
    )


def _set_solver_config_value(
    solver, names: Sequence[str], value: object
) -> str | None:
    """Set the first supported Pyomo solver-config field."""
    config = getattr(solver, "config", None)
    if config is None:
        return None
    for name in names:
        if hasattr(config, name):
            setattr(config, name, value)
            return name
    return None


def _solver_runtime_option_keys(solver_name: str) -> dict[str, str | None]:
    """Return native option keys for gap, threads, and elapsed-time limit."""
    mappings = {
        "cbc": {
            "relative_gap": "ratioGap",
            "threads": "threads",
            "time_limit_seconds": "seconds",
        },
        "cplex": {
            "relative_gap": "mipgap",
            "threads": "threads",
            "time_limit_seconds": "timelimit",
        },
        "cplex_direct": {
            "relative_gap": "mip_tolerances_mipgap",
            "threads": "threads",
            "time_limit_seconds": "timelimit",
        },
        "cplex_persistent": {
            "relative_gap": "mip_tolerances_mipgap",
            "threads": "threads",
            "time_limit_seconds": "timelimit",
        },
        "appsi_cplex": {
            "relative_gap": "mip_tolerances_mipgap",
            "threads": "threads",
            "time_limit_seconds": "timelimit",
        },
        "highs": {
            "relative_gap": "mip_rel_gap",
            "threads": "threads",
            "time_limit_seconds": "time_limit",
        },
        "appsi_highs": {
            "relative_gap": "mip_rel_gap",
            "threads": "threads",
            "time_limit_seconds": "time_limit",
        },
        "gurobi": {
            "relative_gap": "MIPGap",
            "threads": "Threads",
            "time_limit_seconds": "TimeLimit",
        },
        "gurobi_direct": {
            "relative_gap": "MIPGap",
            "threads": "Threads",
            "time_limit_seconds": "TimeLimit",
        },
        "gurobi_persistent": {
            "relative_gap": "MIPGap",
            "threads": "Threads",
            "time_limit_seconds": "TimeLimit",
        },
        "glpk": {
            "relative_gap": "mipgap",
            "threads": None,
            "time_limit_seconds": "tmlim",
        },
    }
    return mappings.get(
        solver_name,
        {
            "relative_gap": None,
            "threads": None,
            "time_limit_seconds": None,
        },
    )


def solve_model(
    model,
    solver_name: str = "cbc",
    *,
    relative_gap: float = 0.01,
    threads: int | None = None,
    time_limit_seconds: float | None = None,
    executable_path: str | Path | None = None,
    tee: bool = False,
):
    """Solve a Pyomo model with reproducible runtime controls.

    Parameters
    ----------
    relative_gap:
        Requested relative MIP optimality gap.
    threads:
        Maximum solver threads. ``None`` leaves the solver default unchanged.
        A positive integer is translated to the native option for CPLEX,
        HiGHS, CBC, and supported Gurobi interfaces.
    time_limit_seconds:
        Optional elapsed-time limit translated to the native solver option.
    """
    _, SolverFactory = _require_pyomo()
    solver_name = str(solver_name).lower()

    relative_gap = float(relative_gap)
    if relative_gap < 0.0:
        raise ValueError("relative_gap must be non-negative.")

    if threads is not None:
        if isinstance(threads, bool) or int(threads) != threads or int(threads) < 1:
            raise ValueError("threads must be a positive integer or None.")
        threads = int(threads)

    if time_limit_seconds is not None:
        time_limit_seconds = float(time_limit_seconds)
        if time_limit_seconds <= 0.0:
            raise ValueError("time_limit_seconds must be positive or None.")

    if executable_path is not None and not Path(executable_path).exists():
        raise FileNotFoundError(f"Solver executable not found: {executable_path}")

    # Appsi interfaces are Python bindings and do not accept Pyomo's
    # ``executable`` keyword.  More generally, some SolverFactory plugins
    # reject the keyword even when its value is ``None``.  Therefore pass it
    # only when the caller supplied a concrete path for a compatible
    # executable-based interface.
    solver_factory_kwargs: dict[str, object] = {}
    if executable_path is not None:
        if solver_name.startswith("appsi_"):
            raise ValueError(
                f"Solver interface {solver_name!r} does not accept "
                "executable_path. Install its Python solver binding and "
                "leave executable_path=None, or select an executable-based "
                "Pyomo interface."
            )
        solver_factory_kwargs["executable"] = str(executable_path)

    solver = SolverFactory(solver_name, **solver_factory_kwargs)
    if solver is None or not solver.available(exception_flag=False):
        raise RuntimeError(
            f"Solver {solver_name!r} is not available. Install/configure it "
            "or provide executable_path."
        )

    option_keys = _solver_runtime_option_keys(solver_name)
    configured_options: dict[str, object] = {}

    gap_config = _set_solver_config_value(
        solver, ("rel_gap", "mip_gap"), relative_gap
    )
    if gap_config is not None:
        configured_options[f"config.{gap_config}"] = relative_gap
    else:
        gap_key = option_keys["relative_gap"]
        if gap_key is not None:
            _set_solver_option(solver, gap_key, relative_gap)
            configured_options[gap_key] = relative_gap

    if threads is not None:
        thread_config = _set_solver_config_value(
            solver, ("threads",), threads
        )
        if thread_config is not None:
            configured_options[f"config.{thread_config}"] = threads
        else:
            thread_key = option_keys["threads"]
            if thread_key is None:
                raise ValueError(
                    f"Treemün does not expose a thread option for solver "
                    f"{solver_name!r}. Leave threads=None or select CPLEX, "
                    "HiGHS, CBC, or Gurobi."
                )
            _set_solver_option(solver, thread_key, threads)
            configured_options[thread_key] = threads

    if time_limit_seconds is not None:
        time_config = _set_solver_config_value(
            solver, ("time_limit",), time_limit_seconds
        )
        if time_config is not None:
            configured_options[f"config.{time_config}"] = (
                time_limit_seconds
            )
        else:
            time_key = option_keys["time_limit_seconds"]
            if time_key is None:
                raise ValueError(
                    f"Treemün does not expose a time-limit option for solver "
                    f"{solver_name!r}."
                )
            _set_solver_option(solver, time_key, time_limit_seconds)
            configured_options[time_key] = time_limit_seconds

    solve_started = perf_counter()
    results = solver.solve(model, tee=tee)
    elapsed = float(perf_counter() - solve_started)
    history = list(getattr(model, "_treemun_solve_history", []))
    history.append(
        {
            "solver_name": solver_name,
            "solve_time_seconds": elapsed,
            "termination_condition": str(
                results.solver.termination_condition
            ),
            "relative_gap_requested": relative_gap,
            "threads_requested": threads,
            "time_limit_seconds_requested": time_limit_seconds,
            "configured_solver_options": configured_options,
        }
    )
    model._treemun_solve_history = history
    return results

def extract_solution(model, results=None, *, selection_tolerance: float = 1e-6) -> dict:
    """Extract objective values, selected policies, and annual harvests."""
    pyo, _ = _require_pyomo()
    if results is not None:
        termination = str(results.solver.termination_condition)
        if termination.lower() not in {"optimal", "feasible", "locallyoptimal"}:
            raise RuntimeError(f"No usable solution was found: {termination}")
    else:
        termination = "not_provided"

    selected_records: list[dict[str, object]] = []
    metadata_frame = pd.DataFrame(model._treemun_metadata["policy_summary"])
    metadata_index = {
        (str(row.stand_id), str(row.policy)): row._asdict()
        for row in metadata_frame.itertuples(index=False)
    }
    for alternative in model.ALTERNATIVES:
        variable_value = pyo.value(model.select_policy[alternative], exception=False)
        if variable_value is not None and variable_value > selection_tolerance:
            record = dict(metadata_index.get(tuple(alternative), {}))
            record["selection_value"] = float(variable_value)
            record["ending_dry_wood_t"] = float(
                model._treemun_metadata["ending_dry_wood_by_policy"].get(
                    tuple(alternative), 0.0
                )
            )
            record["economic_value"] = float(
                model._treemun_metadata["economic_coefficients"].get(
                    tuple(alternative), 0.0
                )
            )
            selected_records.append(record)

    harvest_schedule = pd.DataFrame(
        {
            "period": [int(period) for period in model.PERIODS],
            "harvested_dry_wood_t": [
                float(pyo.value(model.harvested_dry_wood_t[period]))
                for period in model.PERIODS
            ],
        }
    )
    selected_policies = pd.DataFrame(selected_records)
    selected_keys = {
        (str(row["stand_id"]), str(row["policy"]))
        for row in selected_records
        if "stand_id" in row and "policy" in row
    }
    economic_summary = model._treemun_metadata.get("economic_summary_by_policy")
    if economic_summary is not None:
        selected_economic_summary = economic_summary.loc[
            economic_summary.apply(
                lambda row: (str(row["stand_id"]), str(row["policy"]))
                in selected_keys,
                axis=1,
            )
        ].reset_index(drop=True)
    else:
        selected_economic_summary = None

    economic_cash_flow = model._treemun_metadata.get("economic_cash_flow_table")
    if economic_cash_flow is not None:
        selected_economic_cash_flow = economic_cash_flow.loc[
            economic_cash_flow.apply(
                lambda row: (str(row["stand_id"]), str(row["policy"]))
                in selected_keys,
                axis=1,
            )
        ].reset_index(drop=True)
    else:
        selected_economic_cash_flow = None

    economic_value = float(pyo.value(model.economic_value))
    solve_history = list(getattr(model, "_treemun_solve_history", []))
    solve_time_seconds = float(
        sum(item.get("solve_time_seconds", 0.0) for item in solve_history)
    )
    model_build_time_seconds = float(
        model._treemun_metadata.get("model_build_time_seconds", 0.0)
        + model._treemun_metadata.get(
            "spatial_extension_build_time_seconds", 0.0
        )
    )
    greenup_event_conflict_count = (
        float(pyo.value(model.greenup_event_conflict_value))
        if hasattr(model, "greenup_event_conflict_value")
        else (
            float(pyo.value(model.spatial_conflict_value))
            if hasattr(model, "spatial_conflict_value")
            else None
        )
    )
    return {
        "termination_condition": termination,
        "objective_mode": model._treemun_metadata["objective"],
        "objective_value": float(pyo.value(model.objective)),
        "economic_mode": model._treemun_metadata["economic_mode"],
        "economic_metric": model._treemun_metadata["economic_metric"],
        "economic_value": economic_value,
        # Compatibility alias retained for older notebooks. It is a true NPV
        # only when economic_mode == 'detailed_cash_flow'.
        "npv_value": economic_value,
        "discounted_revenue": (
            economic_value
            if model._treemun_metadata["economic_metric"] == "discounted_revenue"
            else None
        ),
        "discounted_net_margin": (
            economic_value
            if model._treemun_metadata["economic_metric"] == "discounted_net_margin"
            else None
        ),
        "net_present_value": (
            economic_value
            if model._treemun_metadata["economic_metric"] == "net_present_value"
            else None
        ),
        "carbon_stock_time_tC_year": float(
            pyo.value(model.carbon_stock_time_value)
        ),
        "ending_dry_wood_t": float(pyo.value(model.ending_dry_wood_t)),
        "ending_carbon_tC": (
            float(pyo.value(model.ending_carbon_tC))
            if hasattr(model, "ending_carbon_tC")
            else None
        ),
        "normalized_npv_value": (
            float(economic_value - model._treemun_metadata["npv_reference"])
            / model._treemun_metadata["npv_scale"]
        ),
        "normalized_economic_value": (
            float(economic_value - model._treemun_metadata["npv_reference"])
            / model._treemun_metadata["npv_scale"]
        ),
        "normalized_carbon_value": (
            float(
                pyo.value(model.carbon_stock_time_value)
                - model._treemun_metadata["carbon_reference"]
            )
            / model._treemun_metadata["carbon_scale"]
        ),
        "greenup_event_conflict_count": greenup_event_conflict_count,
        # Backward-compatible alias.
        "spatial_conflict_value": greenup_event_conflict_count,
        "model_build_time_seconds": model_build_time_seconds,
        "solve_time_seconds": solve_time_seconds,
        "total_model_time_seconds": (
            model_build_time_seconds + solve_time_seconds
        ),
        "number_of_solver_calls": len(solve_history),
        "solver_name": (
            solve_history[-1]["solver_name"] if solve_history else None
        ),
        "threads_requested": (
            solve_history[-1].get("threads_requested")
            if solve_history
            else None
        ),
        "time_limit_seconds_requested": (
            solve_history[-1].get("time_limit_seconds_requested")
            if solve_history
            else None
        ),
        "relative_gap_requested": (
            solve_history[-1].get("relative_gap_requested")
            if solve_history
            else None
        ),
        "solve_history": solve_history,
        "selected_policies": selected_policies,
        "selected_economic_summary": selected_economic_summary,
        "selected_economic_cash_flow": selected_economic_cash_flow,
        "harvest_schedule": harvest_schedule,
    }


extract_results = extract_solution


def build_biobjective_payoff_table(
    *,
    solver_name: str = "cbc",
    solver_options: Mapping[str, object] | None = None,
    model_options: Mapping[str, object],
) -> pd.DataFrame:
    """Solve the economic and carbon anchor models used for normalization.

    The returned payoff table evaluates both criteria at each single-objective
    optimum. It provides a problem-specific approximation of the ideal and
    nadir values for the selected economic metric and standing-wood carbon stock-time.
    """
    records: list[dict[str, object]] = []
    solve_options = dict(solver_options or {})
    base_options = dict(model_options)
    for key in (
        "objective",
        "npv_weight",
        "carbon_weight",
        "npv_scale",
        "carbon_scale",
        "npv_reference",
        "carbon_reference",
    ):
        base_options.pop(key, None)

    for optimized_for in ("economic", "carbon"):
        model = build_forest_management_model(
            **base_options, objective=optimized_for
        )
        results = solve_model(model, solver_name, **solve_options)
        solution = extract_solution(model, results)
        records.append(
            {
                "optimized_for": optimized_for,
                "economic_mode": solution["economic_mode"],
                "economic_metric": solution["economic_metric"],
                "economic_value": solution["economic_value"],
                "npv_value": solution["npv_value"],
                "carbon_stock_time_tC_year": solution[
                    "carbon_stock_time_tC_year"
                ],
                "ending_dry_wood_t": solution["ending_dry_wood_t"],
                "model_build_time_seconds": solution["model_build_time_seconds"],
                "solve_time_seconds": solution["solve_time_seconds"],
                "total_model_time_seconds": solution["total_model_time_seconds"],
                "number_of_solver_calls": solution["number_of_solver_calls"],
                "selected_policies": solution["selected_policies"],
            }
        )
    return pd.DataFrame(records)


def biobjective_normalization_from_payoff(
    payoff_table: pd.DataFrame,
) -> dict[str, float]:
    """Return ideal-nadir range normalization values from a payoff table."""
    economic_column = (
        "economic_value" if "economic_value" in payoff_table.columns else "npv_value"
    )
    required = {economic_column, "carbon_stock_time_tC_year"}
    missing = required - set(payoff_table.columns)
    if missing:
        raise ValueError(f"payoff_table is missing columns: {sorted(missing)}")

    npv_reference = float(payoff_table[economic_column].min())
    carbon_reference = float(
        payoff_table["carbon_stock_time_tC_year"].min()
    )
    npv_scale = max(
        float(payoff_table[economic_column].max()) - npv_reference, 1.0
    )
    carbon_scale = max(
        float(payoff_table["carbon_stock_time_tC_year"].max())
        - carbon_reference,
        1.0,
    )
    return {
        "npv_reference": npv_reference,
        "carbon_reference": carbon_reference,
        "npv_scale": npv_scale,
        "carbon_scale": carbon_scale,
    }


def build_weighted_pareto_front(
    *,
    weights: Iterable[float],
    solver_name: str = "cbc",
    solver_options: Mapping[str, object] | None = None,
    model_options: Mapping[str, object],
    normalization: str = "payoff_range",
    payoff_table: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Solve weighted NPV-carbon models over supplied NPV weights.

    ``normalization='payoff_range'`` is the recommended mode. It computes or
    accepts a two-row payoff table and scales both objectives by their
    problem-specific ideal-nadir ranges. ``normalization='assignment_bounds'``
    uses the analytical stand-assignment bounds calculated by the model builder.
    """
    normalization = str(normalization).strip().lower()
    if normalization not in {"payoff_range", "assignment_bounds"}:
        raise ValueError(
            "normalization must be 'payoff_range' or 'assignment_bounds'."
        )

    records: list[dict[str, object]] = []
    options = dict(solver_options or {})
    base_options = dict(model_options)
    for key in ("objective", "npv_weight", "carbon_weight"):
        base_options.pop(key, None)

    normalization_values: dict[str, float] | None = None
    if normalization == "payoff_range":
        if payoff_table is None:
            payoff_table = build_biobjective_payoff_table(
                solver_name=solver_name,
                solver_options=options,
                model_options=base_options,
            )
        normalization_values = biobjective_normalization_from_payoff(
            payoff_table
        )
        for key, value in normalization_values.items():
            base_options[key] = value

    for npv_weight in weights:
        weight = float(npv_weight)
        if not 0.0 <= weight <= 1.0:
            raise ValueError("Each NPV weight must be between zero and one.")
        model = build_forest_management_model(
            **base_options,
            objective="weighted",
            npv_weight=weight,
            carbon_weight=1.0 - weight,
        )
        results = solve_model(model, solver_name, **options)
        solution = extract_solution(model, results)
        records.append(
            {
                "npv_weight": weight,
                "carbon_weight": 1.0 - weight,
                "economic_mode": solution["economic_mode"],
                "economic_metric": solution["economic_metric"],
                "economic_value": solution["economic_value"],
                "npv_value": solution["npv_value"],
                "carbon_stock_time_tC_year": solution[
                    "carbon_stock_time_tC_year"
                ],
                "normalized_npv_value": solution[
                    "normalized_npv_value"
                ],
                "normalized_carbon_value": solution[
                    "normalized_carbon_value"
                ],
                "ending_dry_wood_t": solution["ending_dry_wood_t"],
                "model_build_time_seconds": solution["model_build_time_seconds"],
                "solve_time_seconds": solution["solve_time_seconds"],
                "total_model_time_seconds": solution["total_model_time_seconds"],
                "number_of_solver_calls": solution["number_of_solver_calls"],
                "selected_policies": solution["selected_policies"],
                "normalization": normalization,
            }
        )
    result = pd.DataFrame(records).sort_values("npv_weight").reset_index(drop=True)
    if payoff_table is not None:
        result.attrs["payoff_table"] = payoff_table
    if normalization_values is not None:
        result.attrs["normalization_values"] = normalization_values
    return result


def build_epsilon_constraint_front(
    *,
    epsilon_objective: str = "carbon",
    epsilon_values: Sequence[float] | None = None,
    number_of_points: int = 11,
    payoff_table: pd.DataFrame | None = None,
    solver_name: str = "cbc",
    solver_options: Mapping[str, object] | None = None,
    model_options: Mapping[str, object],
) -> pd.DataFrame:
    """Build a two-objective NPV-carbon epsilon-constraint front.

    Parameters
    ----------
    epsilon_objective:
        ``"carbon"`` maximizes NPV subject to a minimum carbon stock-time.
        ``"npv"`` maximizes carbon stock-time subject to a minimum NPV.
    epsilon_values:
        Explicit lower bounds. When omitted, anchor solutions are used to
        generate ``number_of_points`` evenly spaced bounds.
    """
    pyo, _ = _require_pyomo()
    import numpy as np

    epsilon_objective = str(epsilon_objective).strip().lower()
    if epsilon_objective not in {"carbon", "npv"}:
        raise ValueError("epsilon_objective must be 'carbon' or 'npv'.")
    if int(number_of_points) < 2:
        raise ValueError("number_of_points must be at least two.")

    solve_options = dict(solver_options or {})
    base_options = dict(model_options)
    base_options.pop("objective", None)
    base_options.pop("npv_weight", None)
    base_options.pop("carbon_weight", None)

    if epsilon_values is None:
        if payoff_table is not None:
            anchors = pd.DataFrame(payoff_table)
            required = {
                "optimized_for",
                "economic_value",
                "carbon_stock_time_tC_year",
            }
            missing = required - set(anchors.columns)
            if missing:
                raise ValueError(
                    f"payoff_table is missing columns: {sorted(missing)}"
                )
            economic_row = anchors.loc[
                anchors["optimized_for"].eq("economic")
            ]
            carbon_row = anchors.loc[anchors["optimized_for"].eq("carbon")]
            if len(economic_row) != 1 or len(carbon_row) != 1:
                raise ValueError(
                    "payoff_table must contain one economic and one carbon anchor."
                )
            if epsilon_objective == "carbon":
                lower = float(
                    economic_row.iloc[0]["carbon_stock_time_tC_year"]
                )
                upper = float(
                    carbon_row.iloc[0]["carbon_stock_time_tC_year"]
                )
            else:
                lower = float(carbon_row.iloc[0]["economic_value"])
                upper = float(economic_row.iloc[0]["economic_value"])
        else:
            npv_model = build_forest_management_model(
                **base_options, objective="economic"
            )
            npv_results = solve_model(npv_model, solver_name, **solve_options)
            npv_anchor = extract_solution(npv_model, npv_results)

            carbon_model = build_forest_management_model(
                **base_options, objective="carbon"
            )
            carbon_results = solve_model(
                carbon_model, solver_name, **solve_options
            )
            carbon_anchor = extract_solution(carbon_model, carbon_results)

            if epsilon_objective == "carbon":
                lower = npv_anchor["carbon_stock_time_tC_year"]
                upper = carbon_anchor["carbon_stock_time_tC_year"]
            else:
                lower = carbon_anchor["npv_value"]
                upper = npv_anchor["npv_value"]
        epsilon_values = np.linspace(
            float(lower), float(upper), int(number_of_points)
        )

    records: list[dict[str, object]] = []
    for epsilon in [float(value) for value in epsilon_values]:
        primary_objective = "npv" if epsilon_objective == "carbon" else "carbon"
        model = build_forest_management_model(
            **base_options,
            objective=primary_objective,
        )
        if epsilon_objective == "carbon":
            model.epsilon_carbon_stock_time = pyo.Constraint(
                expr=model.carbon_stock_time_value >= epsilon
            )
        else:
            model.epsilon_npv = pyo.Constraint(expr=model.npv_value >= epsilon)

        results = solve_model(model, solver_name, **solve_options)
        solution = extract_solution(model, results)
        records.append(
            {
                "epsilon_objective": epsilon_objective,
                "epsilon_value": epsilon,
                "economic_mode": solution["economic_mode"],
                "economic_metric": solution["economic_metric"],
                "economic_value": solution["economic_value"],
                "npv_value": solution["npv_value"],
                "carbon_stock_time_tC_year": solution[
                    "carbon_stock_time_tC_year"
                ],
                "ending_dry_wood_t": solution["ending_dry_wood_t"],
                "model_build_time_seconds": solution["model_build_time_seconds"],
                "solve_time_seconds": solution["solve_time_seconds"],
                "total_model_time_seconds": solution["total_model_time_seconds"],
                "number_of_solver_calls": solution["number_of_solver_calls"],
                "selected_policies": solution["selected_policies"],
            }
        )
    result = pd.DataFrame(records).sort_values(
        "epsilon_value"
    ).reset_index(drop=True)
    if payoff_table is not None:
        result.attrs["payoff_table"] = payoff_table
    return result


def filter_nondominated_points(
    frame: pd.DataFrame,
    *,
    maximize_columns: Sequence[str],
    minimize_columns: Sequence[str] = (),
    tolerance: float = 1e-9,
) -> pd.DataFrame:
    """Return the nondominated subset of a multiobjective result table."""
    required = set(maximize_columns) | set(minimize_columns)
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"frame is missing columns: {sorted(missing)}")
    if frame.empty:
        return frame.copy()

    values = frame.reset_index(drop=True)
    keep = [True] * len(values)
    for i, row_i in values.iterrows():
        if not keep[i]:
            continue
        for j, row_j in values.iterrows():
            if i == j:
                continue
            weakly_better = True
            strictly_better = False
            for column in maximize_columns:
                value_i = float(row_i[column])
                value_j = float(row_j[column])
                if value_j < value_i - tolerance:
                    weakly_better = False
                    break
                if value_j > value_i + tolerance:
                    strictly_better = True
            if not weakly_better:
                continue
            for column in minimize_columns:
                value_i = float(row_i[column])
                value_j = float(row_j[column])
                if value_j > value_i + tolerance:
                    weakly_better = False
                    break
                if value_j < value_i - tolerance:
                    strictly_better = True
            if weakly_better and strictly_better:
                keep[i] = False
                break

    result = values.loc[keep].copy()
    result = result.drop_duplicates(list(required)).reset_index(drop=True)
    return result


def identify_three_objective_knee_point(
    front: pd.DataFrame,
    *,
    payoff_table: pd.DataFrame | None = None,
    economic_column: str = "economic_value",
    carbon_column: str = "carbon_stock_time_tC_year",
    conflict_column: str = "greenup_event_conflict_count",
) -> pd.DataFrame:
    """Normalize a 3D front and identify a knee relative to anchor hyperplane.

    Economic value and carbon are maximized; green-up event conflicts are
    minimized. The returned frame contains normalized scores, signed distance
    from the hyperplane through the three anchor points, and ``is_knee_point``.
    If the anchors are degenerate, the closest point to the normalized ideal
    point is selected instead. Plane and normalization metadata are stored in
    ``DataFrame.attrs`` for visualization.
    """
    import numpy as np

    values = pd.DataFrame(front).copy().reset_index(drop=True)
    if conflict_column not in values and "spatial_conflict_value" in values:
        values[conflict_column] = values["spatial_conflict_value"]
    required = {economic_column, carbon_column, conflict_column}
    missing = required - set(values.columns)
    if missing:
        raise ValueError(f"front is missing columns: {sorted(missing)}")
    if values.empty:
        raise ValueError("front cannot be empty.")

    reference = values
    if payoff_table is not None:
        reference = pd.concat([values, pd.DataFrame(payoff_table)], ignore_index=True)
        if conflict_column not in reference and "spatial_conflict_value" in reference:
            reference[conflict_column] = reference["spatial_conflict_value"]

    bounds = {
        economic_column: (float(reference[economic_column].min()), float(reference[economic_column].max())),
        carbon_column: (float(reference[carbon_column].min()), float(reference[carbon_column].max())),
        conflict_column: (float(reference[conflict_column].min()), float(reference[conflict_column].max())),
    }

    def maximize_score(series, column):
        lower, upper = bounds[column]
        if upper - lower <= 1e-12:
            return pd.Series(1.0, index=series.index)
        return (series.astype(float) - lower) / (upper - lower)

    def minimize_score(series, column):
        lower, upper = bounds[column]
        if upper - lower <= 1e-12:
            return pd.Series(1.0, index=series.index)
        return (upper - series.astype(float)) / (upper - lower)

    values["normalized_economic_score"] = maximize_score(values[economic_column], economic_column)
    values["normalized_carbon_score"] = maximize_score(values[carbon_column], carbon_column)
    values["normalized_greenup_score"] = minimize_score(values[conflict_column], conflict_column)
    coordinates = values[[
        "normalized_economic_score",
        "normalized_carbon_score",
        "normalized_greenup_score",
    ]].to_numpy(dtype=float)

    anchor_coordinates = None
    if payoff_table is not None and "optimized_for" in payoff_table.columns:
        anchors = pd.DataFrame(payoff_table).copy()
        if conflict_column not in anchors and "spatial_conflict_value" in anchors:
            anchors[conflict_column] = anchors["spatial_conflict_value"]
        anchor_aliases = {
            "economic": "economic",
            "carbon": "carbon",
            "greenup_event_conflicts": "greenup",
            "spatial_conflict": "greenup",
        }
        anchor_rows = {}
        for row in anchors.itertuples(index=False):
            key = anchor_aliases.get(str(row.optimized_for))
            if key is not None:
                anchor_rows[key] = row
        if set(anchor_rows) == {"economic", "carbon", "greenup"}:
            anchor_frame = pd.DataFrame([
                anchor_rows["economic"]._asdict(),
                anchor_rows["carbon"]._asdict(),
                anchor_rows["greenup"]._asdict(),
            ])
            anchor_coordinates = np.column_stack([
                maximize_score(anchor_frame[economic_column], economic_column),
                maximize_score(anchor_frame[carbon_column], carbon_column),
                minimize_score(anchor_frame[conflict_column], conflict_column),
            ])

    method = "distance_to_ideal"
    ideal = np.ones(3, dtype=float)
    plane_point = None
    plane_normal = None
    if anchor_coordinates is not None:
        a, b, c = anchor_coordinates
        normal = np.cross(b - a, c - a)
        norm = float(np.linalg.norm(normal))
        if norm > 1e-12:
            normal = normal / norm
            if float(np.dot(ideal - a, normal)) < 0.0:
                normal = -normal
            distances = (coordinates - a) @ normal
            values["knee_score"] = distances
            knee_position = int(np.argmax(distances))
            plane_point = a.tolist()
            plane_normal = normal.tolist()
            method = "maximum_distance_from_anchor_hyperplane"
        else:
            distances = np.linalg.norm(coordinates - ideal, axis=1)
            values["knee_score"] = -distances
            knee_position = int(np.argmin(distances))
    else:
        distances = np.linalg.norm(coordinates - ideal, axis=1)
        values["knee_score"] = -distances
        knee_position = int(np.argmin(distances))

    values["distance_to_normalized_ideal"] = np.linalg.norm(
        coordinates - ideal, axis=1
    )
    values["is_knee_point"] = False
    values.loc[knee_position, "is_knee_point"] = True
    values.attrs["knee_index"] = knee_position
    values.attrs["knee_method"] = method
    values.attrs["normalization_bounds"] = bounds
    values.attrs["anchor_plane_point"] = plane_point
    values.attrs["anchor_plane_normal"] = plane_normal
    return values


def _termination_is_usable(results) -> bool:
    termination = str(results.solver.termination_condition).lower()
    return termination in {"optimal", "feasible", "locallyoptimal"}


def build_three_objective_payoff_table(
    *,
    adjacency_edges,
    final_harvest_indicator: Mapping[tuple[str, str, int], int],
    greenup_window: int = 0,
    weight_by_shared_boundary: bool = False,
    biobjective_payoff_table: pd.DataFrame | None = None,
    solver_name: str = "cbc",
    solver_options: Mapping[str, object] | None = None,
    model_options: Mapping[str, object],
) -> pd.DataFrame:
    """Build economic, carbon, and green-up event-conflict anchors.

    Economic and carbon anchors do not need spatial conflict variables. When a
    bi-objective payoff table is supplied, those two previously solved anchors
    are reused and their realized green-up event conflicts are counted directly.
    Only the green-up anchor then requires two spatial MILP solves: conflict
    minimization followed by an economic lexicographic tie-break.
    """
    pyo, _ = _require_pyomo()
    from .spatial_constraints import (
        add_greenup_event_conflict_measure,
        count_greenup_event_conflicts,
    )

    function_started = perf_counter()
    solve_options = dict(solver_options or {})
    base_options = dict(model_options)
    for key in (
        "objective",
        "npv_weight",
        "carbon_weight",
        "npv_scale",
        "carbon_scale",
        "npv_reference",
        "carbon_reference",
    ):
        base_options.pop(key, None)

    forest = base_options.get("forest")
    if forest is None:
        raise ValueError(
            "model_options must include forest to evaluate realized green-up "
            "event conflicts efficiently."
        )

    def realized_greenup_value(selected_policies: pd.DataFrame) -> float:
        conflicts = count_greenup_event_conflicts(
            selected_policies=selected_policies,
            forest=forest,
            adjacency_edges=adjacency_edges,
            greenup_window=greenup_window,
        )
        if conflicts.empty:
            return 0.0
        if weight_by_shared_boundary:
            return float(conflicts["shared_boundary_length"].sum())
        return float(len(conflicts))

    records: list[dict[str, object]] = []
    reused = None
    if biobjective_payoff_table is not None:
        reused = pd.DataFrame(biobjective_payoff_table).copy()
        required = {
            "optimized_for",
            "economic_value",
            "carbon_stock_time_tC_year",
            "ending_dry_wood_t",
            "selected_policies",
        }
        missing = required - set(reused.columns)
        if missing:
            raise ValueError(
                "biobjective_payoff_table is missing columns: "
                f"{sorted(missing)}"
            )

    for optimized_for in ("economic", "carbon"):
        if reused is not None:
            matches = reused.loc[reused["optimized_for"].eq(optimized_for)]
            if len(matches) != 1:
                raise ValueError(
                    "biobjective_payoff_table must contain exactly one row "
                    f"optimized for {optimized_for!r}."
                )
            row = matches.iloc[0]
            selected = row["selected_policies"]
            greenup_value = realized_greenup_value(selected)
            records.append(
                {
                    "optimized_for": optimized_for,
                    "economic_mode": row.get(
                        "economic_mode", base_options.get("economic_mode")
                    ),
                    "economic_metric": row.get("economic_metric"),
                    "economic_value": float(row["economic_value"]),
                    "npv_value": float(
                        row.get("npv_value", row["economic_value"])
                    ),
                    "carbon_stock_time_tC_year": float(
                        row["carbon_stock_time_tC_year"]
                    ),
                    "greenup_event_conflict_count": greenup_value,
                    "spatial_conflict_value": greenup_value,
                    "ending_dry_wood_t": float(row["ending_dry_wood_t"]),
                    "model_build_time_seconds": float(
                        row.get("model_build_time_seconds", 0.0)
                    ),
                    "solve_time_seconds": float(
                        row.get("solve_time_seconds", 0.0)
                    ),
                    "total_model_time_seconds": float(
                        row.get("total_model_time_seconds", 0.0)
                    ),
                    "number_of_solver_calls": int(
                        row.get("number_of_solver_calls", 1)
                    ),
                    "anchor_reused": True,
                    "selected_policies": selected,
                }
            )
        else:
            model = build_forest_management_model(
                **base_options, objective=optimized_for
            )
            results = solve_model(model, solver_name, **solve_options)
            solution = extract_solution(model, results)
            greenup_value = realized_greenup_value(
                solution["selected_policies"]
            )
            records.append(
                {
                    "optimized_for": optimized_for,
                    "economic_mode": solution["economic_mode"],
                    "economic_metric": solution["economic_metric"],
                    "economic_value": solution["economic_value"],
                    "npv_value": solution["npv_value"],
                    "carbon_stock_time_tC_year": solution[
                        "carbon_stock_time_tC_year"
                    ],
                    "greenup_event_conflict_count": greenup_value,
                    "spatial_conflict_value": greenup_value,
                    "ending_dry_wood_t": solution["ending_dry_wood_t"],
                    "model_build_time_seconds": solution[
                        "model_build_time_seconds"
                    ],
                    "solve_time_seconds": solution["solve_time_seconds"],
                    "total_model_time_seconds": solution[
                        "total_model_time_seconds"
                    ],
                    "number_of_solver_calls": solution[
                        "number_of_solver_calls"
                    ],
                    "anchor_reused": False,
                    "selected_policies": solution["selected_policies"],
                }
            )

    model = build_forest_management_model(**base_options, objective="economic")
    add_greenup_event_conflict_measure(
        model,
        adjacency_edges=adjacency_edges,
        final_harvest_indicator=final_harvest_indicator,
        greenup_window=greenup_window,
        weight_by_shared_boundary=weight_by_shared_boundary,
    )
    model.objective.deactivate()
    model.minimize_greenup_event_conflicts = pyo.Objective(
        expr=model.greenup_event_conflict_value, sense=pyo.minimize
    )
    first_results = solve_model(model, solver_name, **solve_options)
    if not _termination_is_usable(first_results):
        raise RuntimeError(
            "The green-up event-conflict anchor model did not return a "
            "usable solution."
        )
    minimum_conflicts = float(pyo.value(model.greenup_event_conflict_value))

    model.minimize_greenup_event_conflicts.deactivate()
    model.minimum_greenup_event_conflicts_tie_break = pyo.Constraint(
        expr=model.greenup_event_conflict_value <= minimum_conflicts + 1e-7
    )
    model.maximize_economic_tie_break = pyo.Objective(
        expr=model.economic_value, sense=pyo.maximize
    )
    results = solve_model(model, solver_name, **solve_options)
    solution = extract_solution(model, results)
    greenup_value = float(solution["greenup_event_conflict_count"])
    records.append(
        {
            "optimized_for": "greenup_event_conflicts",
            "economic_mode": solution["economic_mode"],
            "economic_metric": solution["economic_metric"],
            "economic_value": solution["economic_value"],
            "npv_value": solution["npv_value"],
            "carbon_stock_time_tC_year": solution[
                "carbon_stock_time_tC_year"
            ],
            "greenup_event_conflict_count": greenup_value,
            "spatial_conflict_value": greenup_value,
            "ending_dry_wood_t": solution["ending_dry_wood_t"],
            "model_build_time_seconds": solution[
                "model_build_time_seconds"
            ],
            "solve_time_seconds": solution["solve_time_seconds"],
            "total_model_time_seconds": solution[
                "total_model_time_seconds"
            ],
            "number_of_solver_calls": solution["number_of_solver_calls"],
            "anchor_reused": False,
            "selected_policies": solution["selected_policies"],
        }
    )

    result = pd.DataFrame(records)
    result.attrs["total_elapsed_time_seconds"] = float(
        perf_counter() - function_started
    )
    result.attrs["biobjective_anchors_reused"] = reused is not None
    return result


def build_three_objective_epsilon_front(
    *,
    adjacency_edges,
    final_harvest_indicator: Mapping[tuple[str, str, int], int],
    greenup_window: int = 0,
    weight_by_shared_boundary: bool = False,
    carbon_epsilon_values: Sequence[float] | None = None,
    greenup_event_conflict_epsilon_values: Sequence[float] | None = None,
    conflict_epsilon_values: Sequence[float] | None = None,
    number_of_carbon_points: int = 3,
    number_of_conflict_points: int = 2,
    number_of_greenup_points: int | None = None,
    payoff_table: pd.DataFrame | None = None,
    solver_name: str = "cbc",
    solver_options: Mapping[str, object] | None = None,
    model_options: Mapping[str, object],
    filter_nondominated: bool = True,
    reuse_payoff_anchors: bool = True,
    reuse_cached_solutions: bool = True,
    reuse_tolerance: float = 1e-7,
) -> pd.DataFrame:
    """Build an efficient three-objective epsilon-constraint front.

    Economic value is maximized subject to a minimum carbon stock-time and a
    maximum number (or weight) of green-up event conflicts. The routine avoids
    redundant MILP solves whenever a previously optimal solution is proven to
    remain optimal for a stricter epsilon combination. In particular, it can
    reuse the global economic anchor and the lexicographic minimum-green-up
    anchor supplied in ``payoff_table``.

    Returned rows identify their origin through ``solution_source``. Reused
    rows report zero model-build and solver time for this front invocation.
    """
    pyo, _ = _require_pyomo()
    import numpy as np

    from .spatial_constraints import add_greenup_event_conflict_measure

    function_started = perf_counter()
    reuse_tolerance = float(reuse_tolerance)
    if reuse_tolerance < 0.0:
        raise ValueError("reuse_tolerance must be non-negative.")
    if number_of_greenup_points is not None:
        number_of_conflict_points = int(number_of_greenup_points)
    if int(number_of_carbon_points) < 2:
        raise ValueError("number_of_carbon_points must be at least two.")
    if int(number_of_conflict_points) < 2:
        raise ValueError("number_of_conflict_points must be at least two.")
    if (
        greenup_event_conflict_epsilon_values is not None
        and conflict_epsilon_values is not None
    ):
        raise ValueError(
            "Provide only one of greenup_event_conflict_epsilon_values or "
            "the deprecated conflict_epsilon_values alias."
        )
    if greenup_event_conflict_epsilon_values is None:
        greenup_event_conflict_epsilon_values = conflict_epsilon_values

    solve_options = dict(solver_options or {})
    base_options = dict(model_options)
    for key in (
        "objective",
        "npv_weight",
        "carbon_weight",
        "npv_scale",
        "carbon_scale",
        "npv_reference",
        "carbon_reference",
    ):
        base_options.pop(key, None)

    if payoff_table is None:
        payoff_table = build_three_objective_payoff_table(
            adjacency_edges=adjacency_edges,
            final_harvest_indicator=final_harvest_indicator,
            greenup_window=greenup_window,
            weight_by_shared_boundary=weight_by_shared_boundary,
            solver_name=solver_name,
            solver_options=solve_options,
            model_options=base_options,
        )

    payoff_table = pd.DataFrame(payoff_table).copy()
    if (
        "greenup_event_conflict_count" not in payoff_table
        and "spatial_conflict_value" in payoff_table
    ):
        payoff_table["greenup_event_conflict_count"] = payoff_table[
            "spatial_conflict_value"
        ]
    required = {
        "optimized_for",
        "economic_value",
        "carbon_stock_time_tC_year",
        "greenup_event_conflict_count",
        "ending_dry_wood_t",
        "selected_policies",
    }
    missing = required - set(payoff_table.columns)
    if missing:
        raise ValueError(f"payoff_table is missing columns: {sorted(missing)}")

    def unique_anchor(name: str) -> pd.Series:
        rows = payoff_table.loc[payoff_table["optimized_for"].eq(name)]
        if len(rows) != 1:
            raise ValueError(
                "payoff_table must contain exactly one row optimized for "
                f"{name!r}."
            )
        return rows.iloc[0]

    economic_anchor = unique_anchor("economic")
    greenup_anchor = unique_anchor("greenup_event_conflicts")

    if carbon_epsilon_values is None:
        carbon_epsilon_values = np.linspace(
            float(payoff_table["carbon_stock_time_tC_year"].min()),
            float(payoff_table["carbon_stock_time_tC_year"].max()),
            int(number_of_carbon_points),
        )
    if greenup_event_conflict_epsilon_values is None:
        lower_conflict = float(
            payoff_table["greenup_event_conflict_count"].min()
        )
        upper_conflict = float(
            payoff_table["greenup_event_conflict_count"].max()
        )
        raw_values = np.linspace(
            lower_conflict,
            upper_conflict,
            int(number_of_conflict_points),
        )
        if weight_by_shared_boundary:
            greenup_event_conflict_epsilon_values = raw_values
        else:
            greenup_event_conflict_epsilon_values = [
                float(round(value)) for value in raw_values
            ]

    carbon_values = sorted(
        {float(value) for value in carbon_epsilon_values}
    )
    # Loosest conflict bound first so its optimum can prove optimality for
    # stricter bounds when it remains feasible.
    greenup_values = sorted(
        {
            float(value)
            for value in greenup_event_conflict_epsilon_values
        },
        reverse=True,
    )

    def scaled_tolerance(*values: float) -> float:
        scale = max([abs(float(value)) for value in values] + [1.0])
        return max(reuse_tolerance, reuse_tolerance * scale)

    def satisfies(row: Mapping[str, object], carbon_bound: float, greenup_bound: float) -> bool:
        carbon_value = float(row["carbon_stock_time_tC_year"])
        greenup_value = float(row["greenup_event_conflict_count"])
        carbon_tol = scaled_tolerance(carbon_value, carbon_bound)
        greenup_tol = scaled_tolerance(greenup_value, greenup_bound)
        return (
            carbon_value + carbon_tol >= carbon_bound
            and greenup_value <= greenup_bound + greenup_tol
        )

    proof_cache: list[dict[str, object]] = []

    def cache_anchor(
        row: pd.Series,
        *,
        source: str,
        source_carbon_bound: float,
        source_greenup_bound: float,
    ) -> None:
        proof_cache.append(
            {
                "solution_source": source,
                "source_carbon_epsilon_tC_year": source_carbon_bound,
                "source_greenup_event_conflict_epsilon": source_greenup_bound,
                "economic_mode": row.get(
                    "economic_mode", base_options.get("economic_mode")
                ),
                "economic_metric": row.get("economic_metric"),
                "economic_value": float(row["economic_value"]),
                "npv_value": float(
                    row.get("npv_value", row["economic_value"])
                ),
                "carbon_stock_time_tC_year": float(
                    row["carbon_stock_time_tC_year"]
                ),
                "greenup_event_conflict_count": float(
                    row["greenup_event_conflict_count"]
                ),
                "ending_dry_wood_t": float(row["ending_dry_wood_t"]),
                "selected_policies": row["selected_policies"],
                "solver_name": row.get("solver_name", solver_name),
            }
        )

    if reuse_payoff_anchors:
        # The global economic optimum is optimal over every epsilon subset in
        # which it remains feasible.
        cache_anchor(
            economic_anchor,
            source="reused_economic_anchor",
            source_carbon_bound=float("-inf"),
            source_greenup_bound=float("inf"),
        )
        # The green-up anchor is computed lexicographically: minimum conflicts,
        # then maximum economic value. It therefore proves optimality for the
        # exact minimum-conflict bound whenever its carbon value is sufficient.
        cache_anchor(
            greenup_anchor,
            source="reused_greenup_anchor",
            source_carbon_bound=float("-inf"),
            source_greenup_bound=float(
                greenup_anchor["greenup_event_conflict_count"]
            ),
        )

    records: list[dict[str, object]] = []
    solved_model_count = 0
    reused_model_count = 0
    infeasible_model_count = 0
    accumulated_model_build_time_seconds = 0.0
    accumulated_solve_time_seconds = 0.0
    accumulated_total_model_time_seconds = 0.0

    def reusable_candidate(
        carbon_bound: float, greenup_bound: float
    ) -> dict[str, object] | None:
        if not (reuse_payoff_anchors or reuse_cached_solutions):
            return None
        candidates: list[dict[str, object]] = []
        for candidate in proof_cache:
            source_carbon = float(
                candidate["source_carbon_epsilon_tC_year"]
            )
            source_greenup = float(
                candidate["source_greenup_event_conflict_epsilon"]
            )
            # The source feasible region must contain the target region.
            carbon_tol = scaled_tolerance(source_carbon, carbon_bound)
            greenup_tol = scaled_tolerance(source_greenup, greenup_bound)
            source_is_superset = (
                source_carbon <= carbon_bound + carbon_tol
                and source_greenup + greenup_tol >= greenup_bound
            )
            if source_is_superset and satisfies(
                candidate, carbon_bound, greenup_bound
            ):
                candidates.append(candidate)
        if not candidates:
            return None
        return max(candidates, key=lambda item: float(item["economic_value"]))

    for carbon_epsilon in carbon_values:
        for greenup_epsilon in greenup_values:
            candidate = reusable_candidate(carbon_epsilon, greenup_epsilon)
            if candidate is not None:
                reused_model_count += 1
                greenup_value = float(
                    candidate["greenup_event_conflict_count"]
                )
                records.append(
                    {
                        "carbon_epsilon_tC_year": carbon_epsilon,
                        "greenup_event_conflict_epsilon": greenup_epsilon,
                        "conflict_epsilon": greenup_epsilon,
                        "economic_mode": candidate["economic_mode"],
                        "economic_metric": candidate["economic_metric"],
                        "economic_value": candidate["economic_value"],
                        "npv_value": candidate["npv_value"],
                        "carbon_stock_time_tC_year": candidate[
                            "carbon_stock_time_tC_year"
                        ],
                        "greenup_event_conflict_count": greenup_value,
                        "spatial_conflict_value": greenup_value,
                        "ending_dry_wood_t": candidate[
                            "ending_dry_wood_t"
                        ],
                        "termination_condition": "optimal_reused",
                        "model_build_time_seconds": 0.0,
                        "solve_time_seconds": 0.0,
                        "total_model_time_seconds": 0.0,
                        "number_of_solver_calls": 0,
                        "solver_name": candidate.get("solver_name"),
                        "solution_source": candidate["solution_source"],
                        "anchor_reused": str(
                            candidate["solution_source"]
                        ).startswith("reused_"),
                        "selected_policies": candidate[
                            "selected_policies"
                        ],
                    }
                )
                continue

            model = build_forest_management_model(
                **base_options, objective="economic"
            )
            add_greenup_event_conflict_measure(
                model,
                adjacency_edges=adjacency_edges,
                final_harvest_indicator=final_harvest_indicator,
                greenup_window=greenup_window,
                weight_by_shared_boundary=weight_by_shared_boundary,
            )
            model.epsilon_carbon_stock_time = pyo.Constraint(
                expr=model.carbon_stock_time_value >= carbon_epsilon
            )
            model.epsilon_greenup_event_conflicts = pyo.Constraint(
                expr=model.greenup_event_conflict_value <= greenup_epsilon
            )

            try:
                results = solve_model(model, solver_name, **solve_options)
            except RuntimeError as exc:
                message = str(exc).lower()
                if "feasible" in message or "solution" in message:
                    infeasible_model_count += 1
                    continue
                raise
            termination = str(results.solver.termination_condition)
            if not _termination_is_usable(results):
                infeasible_model_count += 1
                continue
            solution = extract_solution(model, results)
            solved_model_count += 1
            accumulated_model_build_time_seconds += float(
                solution["model_build_time_seconds"]
            )
            accumulated_solve_time_seconds += float(
                solution["solve_time_seconds"]
            )
            accumulated_total_model_time_seconds += float(
                solution["total_model_time_seconds"]
            )
            greenup_value = float(solution["greenup_event_conflict_count"])
            record = {
                "carbon_epsilon_tC_year": carbon_epsilon,
                "greenup_event_conflict_epsilon": greenup_epsilon,
                "conflict_epsilon": greenup_epsilon,
                "economic_mode": solution["economic_mode"],
                "economic_metric": solution["economic_metric"],
                "economic_value": solution["economic_value"],
                "npv_value": solution["npv_value"],
                "carbon_stock_time_tC_year": solution[
                    "carbon_stock_time_tC_year"
                ],
                "greenup_event_conflict_count": greenup_value,
                "spatial_conflict_value": greenup_value,
                "ending_dry_wood_t": solution["ending_dry_wood_t"],
                "termination_condition": termination,
                "model_build_time_seconds": solution[
                    "model_build_time_seconds"
                ],
                "solve_time_seconds": solution["solve_time_seconds"],
                "total_model_time_seconds": solution[
                    "total_model_time_seconds"
                ],
                "number_of_solver_calls": solution[
                    "number_of_solver_calls"
                ],
                "solver_name": solution["solver_name"],
                "solution_source": "new_epsilon_solve",
                "anchor_reused": False,
                "selected_policies": solution["selected_policies"],
            }
            records.append(record)

            if reuse_cached_solutions:
                proof_cache.append(
                    {
                        "solution_source": "reused_cached_epsilon_solution",
                        "source_carbon_epsilon_tC_year": carbon_epsilon,
                        "source_greenup_event_conflict_epsilon": greenup_epsilon,
                        "economic_mode": solution["economic_mode"],
                        "economic_metric": solution["economic_metric"],
                        "economic_value": solution["economic_value"],
                        "npv_value": solution["npv_value"],
                        "carbon_stock_time_tC_year": solution[
                            "carbon_stock_time_tC_year"
                        ],
                        "greenup_event_conflict_count": greenup_value,
                        "ending_dry_wood_t": solution[
                            "ending_dry_wood_t"
                        ],
                        "selected_policies": solution[
                            "selected_policies"
                        ],
                        "solver_name": solution["solver_name"],
                    }
                )

    requested_combination_count = len(carbon_values) * len(greenup_values)
    result = pd.DataFrame(records)

    def attach_attributes(frame: pd.DataFrame) -> pd.DataFrame:
        frame.attrs["payoff_table"] = payoff_table
        frame.attrs["total_elapsed_time_seconds"] = float(
            perf_counter() - function_started
        )
        frame.attrs["requested_model_count"] = int(
            requested_combination_count
        )
        frame.attrs["requested_combination_count"] = int(
            requested_combination_count
        )
        frame.attrs["solved_model_count"] = int(solved_model_count)
        frame.attrs["reused_model_count"] = int(reused_model_count)
        frame.attrs["avoided_solver_calls"] = int(reused_model_count)
        frame.attrs["infeasible_model_count"] = int(
            infeasible_model_count
        )
        frame.attrs["model_build_time_seconds"] = float(
            accumulated_model_build_time_seconds
        )
        frame.attrs["solve_time_seconds"] = float(
            accumulated_solve_time_seconds
        )
        frame.attrs["total_model_time_seconds"] = float(
            accumulated_total_model_time_seconds
        )
        frame.attrs["reuse_payoff_anchors"] = bool(
            reuse_payoff_anchors
        )
        frame.attrs["reuse_cached_solutions"] = bool(
            reuse_cached_solutions
        )
        return frame

    if result.empty:
        return attach_attributes(result)

    result = result.sort_values(
        [
            "carbon_epsilon_tC_year",
            "greenup_event_conflict_epsilon",
        ],
        ascending=[True, False],
    ).reset_index(drop=True)
    if filter_nondominated:
        result = filter_nondominated_points(
            result,
            maximize_columns=(
                "economic_value",
                "carbon_stock_time_tC_year",
            ),
            minimize_columns=("greenup_event_conflict_count",),
        )
    return attach_attributes(result)


# treemun_sim/multi_epsilon.py
"""
Three-objective epsilon-constraint utilities for treemun-sim.

This module extends the existing NPV-carbon epsilon-constraint workflow by
including spatial adjacency conflict as a third performance dimension.

Objectives/criteria:
    - maximize NPV
    - maximize carbon-stock-change proxy
    - minimize weighted adjacent final-harvest conflict

The main entry points are:
    build_multi_epsilon_front_3d(...)
    plot_multi_epsilon_front_3d(...)

The implementation is intentionally separated from optimization.py so it can be
added safely without modifying the existing Pareto and epsilon front utilities.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from pyomo.environ import Constraint, Objective, Param, maximize, value
from pyomo.opt import TerminationCondition

from .optimization import (
    forest_management_optimization_model,
    solve_model,
    extract_results,
)
from .adjacency_extension import add_final_harvest_adjacency


# ---------------------------------------------------------------------
# Small compatibility and utility helpers
# ---------------------------------------------------------------------


def _safe_float(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _safe_value(obj: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        return _safe_float(value(obj, exception=False), default=default)
    except Exception:
        return default


def _as_list(values: Optional[Sequence[float]]) -> Optional[List[float]]:
    if values is None:
        return None
    return [float(v) for v in values]


def _solve_model_compat(
    model,
    solver_name: str = "cbc",
    executable_path: Optional[str] = None,
    gap: float = 0.01,
    tee: bool = False,
):
    """Call treemun_sim.solve_model while tolerating older signatures."""
    try:
        return solve_model(
            model,
            solver_name=solver_name,
            executable_path=executable_path,
            gap=gap,
            tee=tee,
        )
    except TypeError:
        try:
            return solve_model(
                model,
                solver_name=solver_name,
                gap=gap,
                tee=tee,
            )
        except TypeError:
            return solve_model(model, solver_name=solver_name)


def _active_objective_value(model) -> Optional[float]:
    active_objs = list(model.component_objects(Objective, active=True))
    if not active_objs:
        return None
    return _safe_value(active_objs[0].expr)


def _normalize_primary_objective(primary_objective: str) -> str:
    aliases = {
        "npv": "npv",
        "net_present_value": "npv",
        "net present value": "npv",
        "carbon": "carbon",
        "carbseq": "carbon",
        "carb_seq": "carbon",
        "carbon_seq": "carbon",
        "carbonsequestration": "carbon",
        "carbon_sequestration": "carbon",
    }

    if primary_objective is None:
        return "npv"

    key = str(primary_objective).strip().lower()

    if key not in aliases:
        raise ValueError(
            "primary_objective must be 'npv' or 'carbon'. "
            f"Got {primary_objective!r}."
        )

    return aliases[key]


def _objective_scale(model, objective_name: str) -> float:
    objective_name = _normalize_primary_objective(objective_name)

    if objective_name == "npv":
        scale = _safe_value(getattr(model, "npv_scale", None), None)
        if scale is None:
            scale = abs(_safe_value(getattr(model, "npv_value", None), 1.0))
        return max(abs(float(scale)), 1.0)

    if objective_name == "carbon":
        scale = _safe_value(getattr(model, "carbon_scale", None), None)
        if scale is None:
            scale = abs(_safe_value(getattr(model, "carbon_seq_value", None), 1.0))
        return max(abs(float(scale)), 1.0)

    return 1.0


def _make_base_model(
    bosque,
    a_i_j_T,
    a_i_j_t,
    carbon_i_j_t,
    horizon: int,
    objective: str,
    pine_revenue: Any = 9,
    eucalyptus_revenue: Any = 10,
    min_ending_biomass: float = 30000,
    discount_rate: float = 0.08,
    even_flow_tolerance: float = 0.0,
    npv_weight: float = 0.5,
    carbon_weight: float = 0.5,
    npv_scale: Optional[float] = None,
    carbon_scale: Optional[float] = None,
):
    """Create a base Treemun optimization model using the current API."""
    return forest_management_optimization_model(
        bosque=bosque,
        a_i_j_T=a_i_j_T,
        a_i_j_t=a_i_j_t,
        carbon_i_j_t=carbon_i_j_t,
        horizon=horizon,
        pine_revenue=pine_revenue,
        eucalyptus_revenue=eucalyptus_revenue,
        min_ending_biomass=min_ending_biomass,
        discount_rate=discount_rate,
        even_flow_tolerance=even_flow_tolerance,
        objective=objective,
        npv_weight=npv_weight,
        carbon_weight=carbon_weight,
        npv_scale=npv_scale,
        carbon_scale=carbon_scale,
    )


# ---------------------------------------------------------------------
# Extract selected policies and spatial conflicts
# ---------------------------------------------------------------------


def _extract_selected_policies_from_model(model) -> Dict[str, str]:
    """Extract selected policy by stand from x_pine and x_eucalyptus."""
    selected: Dict[str, str] = {}

    if hasattr(model, "x_pine"):
        for i, j in model.x_pine:
            xval = _safe_value(model.x_pine[i, j])
            if xval is not None and xval > 0.5:
                selected[str(i)] = str(j)

    if hasattr(model, "x_eucalyptus"):
        for i, j in model.x_eucalyptus:
            xval = _safe_value(model.x_eucalyptus[i, j])
            if xval is not None and xval > 0.5:
                selected[str(i)] = str(j)

    return selected


def _species_key_from_policy(policy_name: Any) -> str:
    p = str(policy_name).lower()

    if "pino" in p or "pinus" in p:
        return "Pinus"

    if "euca" in p or "eucalyptus" in p:
        # Preserve the current internal treemun-sim spelling.
        return "Eucapyltus"

    raise ValueError(f"Cannot infer species from policy name: {policy_name!r}")


def _final_harvest_value_for_selected_policy(
    stand_id: Any,
    policy_name: Any,
    period: int,
    final_harvest_indicator: Dict[Tuple[int, str, str, str], int],
) -> int:
    species_key = _species_key_from_policy(policy_name)

    return int(
        final_harvest_indicator.get(
            (int(period), species_key, str(policy_name), str(stand_id)),
            0,
        )
    )


def count_adjacent_final_harvest_conflicts(
    model,
    adjacency_edges,
    final_harvest_indicator: Dict[Tuple[int, str, str, str], int],
    horizon: int,
) -> Tuple[int, float, pd.DataFrame]:
    """
    Count true adjacent final-harvest conflicts from selected x_ij values.

    This is used for reporting because z variables in epsilon models can be
    non-unique when they are only constrained by an upper bound.
    """
    if hasattr(adjacency_edges, "columns"):
        edges_df = adjacency_edges.copy()
    else:
        edges_df = pd.DataFrame(adjacency_edges, columns=["stand_id_1", "stand_id_2"])
        edges_df["shared_boundary_m"] = 1.0

    selected = _extract_selected_policies_from_model(model)
    rows = []

    for _, edge in edges_df.iterrows():
        s = str(edge["stand_id_1"])
        r = str(edge["stand_id_2"])
        w = float(edge.get("shared_boundary_m", edge.get("weight", 1.0)))

        policy_s = selected.get(s)
        policy_r = selected.get(r)

        if policy_s is None or policy_r is None:
            continue

        for t in range(1, int(horizon) + 1):
            ys = _final_harvest_value_for_selected_policy(
                s,
                policy_s,
                t,
                final_harvest_indicator,
            )
            yr = _final_harvest_value_for_selected_policy(
                r,
                policy_r,
                t,
                final_harvest_indicator,
            )

            if ys == 1 and yr == 1:
                rows.append(
                    {
                        "stand_id_1": s,
                        "stand_id_2": r,
                        "period": int(t),
                        "shared_boundary_m": float(w),
                        "policy_1": str(policy_s),
                        "policy_2": str(policy_r),
                    }
                )

    conflicts_df = pd.DataFrame(rows)

    n_conflicts = int(len(conflicts_df))
    weighted_conflicts = (
        float(conflicts_df["shared_boundary_m"].sum())
        if n_conflicts > 0
        else 0.0
    )

    return n_conflicts, weighted_conflicts, conflicts_df


# ---------------------------------------------------------------------
# Epsilon grid builders
# ---------------------------------------------------------------------


def _build_carbon_epsilons(
    carbon_epsilons: Optional[Sequence[float]],
    n_carbon_epsilons: int,
    carbon_epsilon_mode: str,
    carbon_at_npv: float,
    carbon_best: float,
) -> Tuple[List[float], List[Optional[float]]]:
    """Build carbon thresholds for primary_objective='npv'."""
    mode = str(carbon_epsilon_mode).lower()

    low = min(float(carbon_at_npv), float(carbon_best))
    high = max(float(carbon_at_npv), float(carbon_best))

    if carbon_epsilons is None:
        values = np.linspace(low, high, int(n_carbon_epsilons)).tolist()
        rel = [None for _ in values]
        return [float(v) for v in values], rel

    raw = [float(v) for v in carbon_epsilons]

    if mode == "absolute":
        return raw, [None for _ in raw]

    if mode in {"relative", "relative_to_range"}:
        for v in raw:
            if v < 0.0 or v > 1.0:
                raise ValueError(
                    "Relative carbon epsilons must be between 0 and 1."
                )
        values = [low + v * (high - low) for v in raw]
        return values, raw

    raise ValueError(
        "carbon_epsilon_mode must be 'absolute' or 'relative_to_range'."
    )


def _build_npv_epsilons(
    npv_epsilons: Optional[Sequence[float]],
    n_npv_epsilons: int,
    npv_epsilon_mode: str,
    npv_at_carbon: float,
    npv_best: float,
) -> Tuple[List[float], List[Optional[float]]]:
    """Build NPV thresholds for primary_objective='carbon'."""
    mode = str(npv_epsilon_mode).lower()

    low = min(float(npv_at_carbon), float(npv_best))
    high = max(float(npv_at_carbon), float(npv_best))

    if npv_epsilons is None:
        values = np.linspace(low, high, int(n_npv_epsilons)).tolist()
        rel = [None for _ in values]
        return [float(v) for v in values], rel

    raw = [float(v) for v in npv_epsilons]

    if mode == "absolute":
        return raw, [None for _ in raw]

    if mode == "relative":
        if abs(float(npv_best)) < 1e-12:
            raise ValueError("Cannot use relative NPV epsilons because best NPV is zero.")
        for v in raw:
            if v < 0.0 or v > 1.0:
                raise ValueError("Relative NPV epsilons must be between 0 and 1.")
        values = [v * float(npv_best) for v in raw]
        return values, raw

    if mode == "relative_to_range":
        for v in raw:
            if v < 0.0 or v > 1.0:
                raise ValueError("Relative NPV epsilons must be between 0 and 1.")
        values = [low + v * (high - low) for v in raw]
        return values, raw

    raise ValueError(
        "npv_epsilon_mode must be 'absolute', 'relative', or 'relative_to_range'."
    )


def _adjacency_total_scale(adjacency_edges, horizon: int) -> float:
    if hasattr(adjacency_edges, "columns"):
        if "shared_boundary_m" in adjacency_edges.columns:
            total = float(adjacency_edges["shared_boundary_m"].astype(float).sum())
        elif "weight" in adjacency_edges.columns:
            total = float(adjacency_edges["weight"].astype(float).sum())
        else:
            total = float(len(adjacency_edges))
    else:
        total = float(len(list(adjacency_edges)))

    return max(total * int(horizon), 1.0)


def _build_adjacency_epsilons(
    adjacency_epsilons: Optional[Sequence[float]],
    adjacency_epsilon_mode: str,
    adjacency_reference_value: float,
    adjacency_scale: float,
) -> Tuple[List[float], List[Optional[float]]]:
    """Build absolute adjacency upper bounds."""
    mode = str(adjacency_epsilon_mode).lower()

    if adjacency_epsilons is None:
        raw = [1.00, 0.75, 0.50, 0.25, 0.10]
    else:
        raw = [float(v) for v in adjacency_epsilons]

    if mode == "absolute":
        return raw, [None for _ in raw]

    if mode == "relative_to_base":
        base = float(adjacency_reference_value)
        if base <= 1e-12:
            base = float(adjacency_scale)
        return [v * base for v in raw], raw

    if mode == "relative_to_scale":
        return [v * float(adjacency_scale) for v in raw], raw

    raise ValueError(
        "adjacency_epsilon_mode must be 'absolute', 'relative_to_base', "
        "or 'relative_to_scale'."
    )


# ---------------------------------------------------------------------
# Dominance and knee-point diagnostics
# ---------------------------------------------------------------------


def _is_nondominated_3d(
    df: pd.DataFrame,
    npv_col: str = "npv_value",
    carbon_col: str = "carbon_seq_value",
    adjacency_col: str = "adjacency_value",
    tol: float = 1e-9,
) -> np.ndarray:
    """
    Identify non-dominated solutions for max NPV, max carbon, min adjacency.
    """
    values = df[[npv_col, carbon_col, adjacency_col]].to_numpy(dtype=float)
    n = len(values)
    nondominated = np.ones(n, dtype=bool)

    for i in range(n):
        ni, ci, ai = values[i]

        for j in range(n):
            if i == j:
                continue

            nj, cj, aj = values[j]

            dominates = (
                nj >= ni - tol
                and cj >= ci - tol
                and aj <= ai + tol
                and (nj > ni + tol or cj > ci + tol or aj < ai - tol)
            )

            if dominates:
                nondominated[i] = False
                break

    return nondominated


def _identify_knee_3d(
    df: pd.DataFrame,
    npv_col: str = "npv_value",
    carbon_col: str = "carbon_seq_value",
    adjacency_col: str = "adjacency_value",
) -> Optional[Any]:
    """Identify a knee-like point by normalized distance to ideal (1,1,1)."""
    if df.empty:
        return None

    x = df[npv_col].astype(float).to_numpy()
    y = df[carbon_col].astype(float).to_numpy()
    z = df[adjacency_col].astype(float).to_numpy()

    def norm_max(arr):
        lo, hi = np.min(arr), np.max(arr)
        if abs(hi - lo) < 1e-12:
            return np.ones_like(arr)
        return (arr - lo) / (hi - lo)

    def norm_min(arr):
        lo, hi = np.min(arr), np.max(arr)
        if abs(hi - lo) < 1e-12:
            return np.ones_like(arr)
        return (hi - arr) / (hi - lo)

    x_norm = norm_max(x)
    y_norm = norm_max(y)
    z_norm = norm_min(z)

    dist = np.sqrt((1.0 - x_norm) ** 2 + (1.0 - y_norm) ** 2 + (1.0 - z_norm) ** 2)
    pos = int(np.argmin(dist))

    return df.index[pos]


def _add_front_diagnostics(
    front_df: pd.DataFrame,
    identify_knee: bool = True,
    keep_dominated: bool = True,
) -> pd.DataFrame:
    df = front_df.copy()

    if df.empty:
        df["is_nondominated_3d"] = []
        df["is_knee_3d"] = []
        return df

    df["is_nondominated_3d"] = False
    df["is_knee_3d"] = False

    solved_mask = df["solved"] == True

    if solved_mask.any():
        solved = df.loc[solved_mask].copy()

        valid = solved[["npv_value", "carbon_seq_value", "adjacency_value"]].notna().all(axis=1)
        solved_valid = solved.loc[valid].copy()

        if not solved_valid.empty:
            nondom = _is_nondominated_3d(solved_valid)
            nondom_idx = solved_valid.index[nondom]
            df.loc[nondom_idx, "is_nondominated_3d"] = True

            if identify_knee and len(nondom_idx) > 0:
                knee_idx = _identify_knee_3d(df.loc[nondom_idx].copy())
                if knee_idx is not None:
                    df.loc[knee_idx, "is_knee_3d"] = True

    if not keep_dominated:
        df = df[df["is_nondominated_3d"] == True].copy()

    return df.reset_index(drop=True)


# ---------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------


def build_multi_epsilon_front_3d(
    bosque,
    a_i_j_T,
    a_i_j_t,
    carbon_i_j_t,
    horizon: int,
    adjacency_edges,
    final_harvest_indicator: Dict[Tuple[int, str, str, str], int],
    primary_objective: str = "npv",
    carbon_epsilons: Optional[Sequence[float]] = None,
    n_carbon_epsilons: int = 6,
    carbon_epsilon_mode: str = "absolute",
    npv_epsilons: Optional[Sequence[float]] = None,
    n_npv_epsilons: int = 6,
    npv_epsilon_mode: str = "relative",
    adjacency_epsilons: Optional[Sequence[float]] = None,
    adjacency_epsilon_mode: str = "relative_to_base",
    adjacency_reference_objective: str = "weighted",
    reference_npv_weight: float = 0.5,
    reference_carbon_weight: float = 0.5,
    pine_revenue: Any = 9,
    eucalyptus_revenue: Any = 10,
    min_ending_biomass: float = 30000,
    discount_rate: float = 0.08,
    even_flow_tolerance: float = 0.0,
    solver_name: str = "cbc",
    executable_path: Optional[str] = None,
    gap: float = 0.01,
    tee: bool = False,
    make_plot: bool = True,
    identify_knee: bool = True,
    keep_dominated: bool = True,
    save_results: bool = False,
    results_dir: str = "treemun_results",
    run_name: Optional[str] = None,
    save_plot: bool = True,
    plot_dpi: int = 300,
):
    """
    Build a 3D epsilon-constraint solution set for NPV, carbon, and adjacency.

    Supported directions
    --------------------
    primary_objective='npv':
        maximize NPV subject to carbon >= epsilon_C and adjacency <= epsilon_A.

    primary_objective='carbon':
        maximize carbon subject to NPV >= epsilon_NPV and adjacency <= epsilon_A.

    Notes
    -----
    Adjacency is treated as a minimization criterion. The epsilon threshold is
    therefore an upper bound on weighted adjacent final-harvest conflict.

    Returns
    -------
    front_df, fig, ax
        DataFrame with all solved/infeasible runs and optional 3D matplotlib plot.
    """
    if carbon_i_j_t is None:
        raise ValueError("carbon_i_j_t is required for multi-objective epsilon front.")

    primary_objective = _normalize_primary_objective(primary_objective)

    # ------------------------------------------------------------
    # Anchor models for automatic epsilon ranges
    # ------------------------------------------------------------
    model_npv = _make_base_model(
        bosque=bosque,
        a_i_j_T=a_i_j_T,
        a_i_j_t=a_i_j_t,
        carbon_i_j_t=carbon_i_j_t,
        horizon=horizon,
        objective="npv",
        pine_revenue=pine_revenue,
        eucalyptus_revenue=eucalyptus_revenue,
        min_ending_biomass=min_ending_biomass,
        discount_rate=discount_rate,
        even_flow_tolerance=even_flow_tolerance,
    )
    results_npv = _solve_model_compat(
        model_npv,
        solver_name=solver_name,
        executable_path=executable_path,
        gap=gap,
        tee=tee,
    )
    out_npv = extract_results(model_npv, results_npv)
    if out_npv is None:
        raise RuntimeError("Could not solve the pure NPV anchor model.")

    model_carbon = _make_base_model(
        bosque=bosque,
        a_i_j_T=a_i_j_T,
        a_i_j_t=a_i_j_t,
        carbon_i_j_t=carbon_i_j_t,
        horizon=horizon,
        objective="carbon",
        pine_revenue=pine_revenue,
        eucalyptus_revenue=eucalyptus_revenue,
        min_ending_biomass=min_ending_biomass,
        discount_rate=discount_rate,
        even_flow_tolerance=even_flow_tolerance,
    )
    results_carbon = _solve_model_compat(
        model_carbon,
        solver_name=solver_name,
        executable_path=executable_path,
        gap=gap,
        tee=tee,
    )
    out_carbon = extract_results(model_carbon, results_carbon)
    if out_carbon is None:
        raise RuntimeError("Could not solve the pure carbon anchor model.")

    npv_best = float(out_npv["npv_value"])
    carbon_at_npv = float(out_npv["carbon_seq_value"])
    npv_at_carbon = float(out_carbon["npv_value"])
    carbon_best = float(out_carbon["carbon_seq_value"])

    if primary_objective == "npv":
        other_eps_values, other_eps_relative = _build_carbon_epsilons(
            carbon_epsilons=carbon_epsilons,
            n_carbon_epsilons=n_carbon_epsilons,
            carbon_epsilon_mode=carbon_epsilon_mode,
            carbon_at_npv=carbon_at_npv,
            carbon_best=carbon_best,
        )
        other_name = "carbon"
    else:
        other_eps_values, other_eps_relative = _build_npv_epsilons(
            npv_epsilons=npv_epsilons,
            n_npv_epsilons=n_npv_epsilons,
            npv_epsilon_mode=npv_epsilon_mode,
            npv_at_carbon=npv_at_carbon,
            npv_best=npv_best,
        )
        other_name = "npv"

    # ------------------------------------------------------------
    # Adjacency reference and epsilon grid
    # ------------------------------------------------------------
    adjacency_scale = _adjacency_total_scale(adjacency_edges, horizon)

    ref_objective = str(adjacency_reference_objective).lower()
    if ref_objective in {"biobjective", "bi-objective", "biobjetivo"}:
        ref_objective = "weighted"

    if ref_objective not in {"npv", "carbon", "weighted"}:
        raise ValueError(
            "adjacency_reference_objective must be 'npv', 'carbon', or 'weighted'."
        )

    ref_model = _make_base_model(
        bosque=bosque,
        a_i_j_T=a_i_j_T,
        a_i_j_t=a_i_j_t,
        carbon_i_j_t=carbon_i_j_t,
        horizon=horizon,
        objective=ref_objective,
        pine_revenue=pine_revenue,
        eucalyptus_revenue=eucalyptus_revenue,
        min_ending_biomass=min_ending_biomass,
        discount_rate=discount_rate,
        even_flow_tolerance=even_flow_tolerance,
        npv_weight=reference_npv_weight,
        carbon_weight=reference_carbon_weight,
    )
    ref_results = _solve_model_compat(
        ref_model,
        solver_name=solver_name,
        executable_path=executable_path,
        gap=gap,
        tee=tee,
    )
    ref_output = extract_results(ref_model, ref_results)
    if ref_output is None:
        raise RuntimeError("Could not solve the adjacency reference model.")

    _, adjacency_reference_value, _ = count_adjacent_final_harvest_conflicts(
        model=ref_model,
        adjacency_edges=adjacency_edges,
        final_harvest_indicator=final_harvest_indicator,
        horizon=horizon,
    )

    adjacency_eps_values, adjacency_eps_relative = _build_adjacency_epsilons(
        adjacency_epsilons=adjacency_epsilons,
        adjacency_epsilon_mode=adjacency_epsilon_mode,
        adjacency_reference_value=adjacency_reference_value,
        adjacency_scale=adjacency_scale,
    )

    # ------------------------------------------------------------
    # Solve grid
    # ------------------------------------------------------------
    rows = []
    solution_records = []
    model_id = 0

    for eps_other_idx, eps_other in enumerate(other_eps_values):
        eps_other = float(eps_other)
        eps_other_rel = other_eps_relative[eps_other_idx]

        for eps_adj_idx, eps_adj in enumerate(adjacency_eps_values):
            eps_adj = float(eps_adj)
            eps_adj_rel = adjacency_eps_relative[eps_adj_idx]

            label = (
                f"multi_eps_{model_id:03d}_max_{primary_objective}_"
                f"eps_{other_name}_{eps_other_idx:03d}_eps_adj_{eps_adj_idx:03d}"
            )

            t0 = time.time()

            model = _make_base_model(
                bosque=bosque,
                a_i_j_T=a_i_j_T,
                a_i_j_t=a_i_j_t,
                carbon_i_j_t=carbon_i_j_t,
                horizon=horizon,
                objective=primary_objective,
                pine_revenue=pine_revenue,
                eucalyptus_revenue=eucalyptus_revenue,
                min_ending_biomass=min_ending_biomass,
                discount_rate=discount_rate,
                even_flow_tolerance=even_flow_tolerance,
            )

            # Add z variables and adjacency expression, with phi=0.
            base_scale = _objective_scale(model, primary_objective)
            model = add_final_harvest_adjacency(
                model=model,
                final_harvest_indicator=final_harvest_indicator,
                adjacency_edges=adjacency_edges,
                mode="penalty_final_harvest",
                phi=0.0,
                adjacency_weight_col="shared_boundary_m",
                adjacency_scale=adjacency_scale,
                base_objective_scale=base_scale,
                base_objective_is_normalized=False,
            )

            # Add the two epsilon constraints.
            if primary_objective == "npv":
                model.multi_epsilon_carbon_min = Constraint(
                    expr=model.carbon_seq_value >= eps_other
                )
            else:
                model.multi_epsilon_npv_min = Constraint(
                    expr=model.npv_value >= eps_other
                )

            model.multi_epsilon_adjacency_max = Constraint(
                expr=model.adjacency_penalty_value_ext <= eps_adj
            )

            results = _solve_model_compat(
                model,
                solver_name=solver_name,
                executable_path=executable_path,
                gap=gap,
                tee=tee,
            )

            elapsed = time.time() - t0
            output = extract_results(model, results)

            term = str(results.solver.termination_condition)
            status = str(results.solver.status)
            solved = output is not None

            if solved:
                n_conflicts, adj_value, conflicts_df = count_adjacent_final_harvest_conflicts(
                    model=model,
                    adjacency_edges=adjacency_edges,
                    final_harvest_indicator=final_harvest_indicator,
                    horizon=horizon,
                )

                npv_value = _safe_value(model.npv_value)
                carbon_value = _safe_value(model.carbon_seq_value)
                objective_value = _active_objective_value(model)
                adjacency_model_value = _safe_value(model.adjacency_penalty_value_ext)
            else:
                n_conflicts = None
                adj_value = None
                conflicts_df = pd.DataFrame()
                npv_value = None
                carbon_value = None
                objective_value = None
                adjacency_model_value = None

            row = {
                "model_id": model_id,
                "model_label": label,
                "primary_objective": primary_objective,
                "epsilon_on": other_name,
                "epsilon_value": eps_other,
                "epsilon_relative": eps_other_rel,
                "epsilon_carbon": eps_other if other_name == "carbon" else None,
                "epsilon_npv": eps_other if other_name == "npv" else None,
                "epsilon_adjacency": eps_adj,
                "epsilon_adjacency_relative": eps_adj_rel,
                "adjacency_epsilon_mode": adjacency_epsilon_mode,
                "adjacency_reference_value": adjacency_reference_value,
                "adjacency_scale": adjacency_scale,
                "objective_value": objective_value,
                "npv_value": npv_value,
                "carbon_seq_value": carbon_value,
                "adjacency_value": adj_value,
                "adjacency_model_value": adjacency_model_value,
                "adjacent_final_harvest_conflicts": n_conflicts,
                "solver_status": status,
                "termination_condition": term,
                "solved": bool(solved),
                "time_sec": elapsed,
                "npv_best_anchor": npv_best,
                "carbon_at_npv_anchor": carbon_at_npv,
                "npv_at_carbon_anchor": npv_at_carbon,
                "carbon_best_anchor": carbon_best,
            }

            rows.append(row)
            solution_records.append(
                {
                    "model_id": model_id,
                    "model": model,
                    "results": results,
                    "output": output,
                    "conflicts": conflicts_df,
                    "row": row,
                }
            )

            model_id += 1

    front_df = pd.DataFrame(rows)
    front_df = _add_front_diagnostics(
        front_df,
        identify_knee=identify_knee,
        keep_dominated=keep_dominated,
    )

    fig = None
    ax = None

    if make_plot or (save_results and save_plot):
        fig, ax = plot_multi_epsilon_front_3d(
            front_df,
            show_nondominated=True,
            show_knee=identify_knee,
        )

    if save_results:
        metadata = _save_multi_epsilon_results(
            front_df=front_df,
            solution_records=solution_records,
            results_dir=results_dir,
            run_name=run_name,
            fig=fig,
            save_plot=save_plot,
            plot_dpi=plot_dpi,
        )
        front_df.attrs["saved_results_dir"] = metadata["run_dir"]
        front_df.attrs["front_plot_png"] = metadata.get("front_plot_png")

    return front_df, fig, ax


# ---------------------------------------------------------------------
# Plotting and save utilities
# ---------------------------------------------------------------------


def plot_multi_epsilon_front_3d(
    front_df: pd.DataFrame,
    x_col: str = "npv_value",
    y_col: str = "carbon_seq_value",
    z_col: str = "adjacency_value",
    color_col: Optional[str] = "epsilon_adjacency_relative",
    show_nondominated: bool = True,
    show_knee: bool = True,
    annotate: bool = False,
    invert_z_axis: bool = False,
    title: str = "3D epsilon-constraint front: NPV, carbon, and adjacency",
    figsize: Tuple[float, float] = (9, 7),
):
    """
    Plot the 3D epsilon-constraint solution set.

    By default, z_col is adjacency_value. Lower values on that axis are better.
    """
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

    if front_df is None or front_df.empty:
        raise ValueError("front_df is empty.")

    df = front_df.copy()
    df = df[df.get("solved", False) == True].copy()
    df = df[df[[x_col, y_col, z_col]].notna().all(axis=1)].copy()

    if df.empty:
        raise ValueError("front_df has no solved rows with valid x/y/z values.")

    x = pd.to_numeric(df[x_col], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(df[y_col], errors="coerce").to_numpy(dtype=float)
    z = pd.to_numeric(df[z_col], errors="coerce").to_numpy(dtype=float)

    fig = plt.figure(figsize=figsize)
    ax = fig.add_subplot(111, projection="3d")

    if color_col is not None and color_col in df.columns:
        c = pd.to_numeric(df[color_col], errors="coerce").to_numpy(dtype=float)
        sc = ax.scatter(x, y, z, c=c, marker="o", s=45, label="Solved solutions")
        cbar = fig.colorbar(sc, ax=ax, shrink=0.65, pad=0.10)
        cbar.set_label(color_col)
    else:
        ax.scatter(x, y, z, marker="o", s=45, label="Solved solutions")

    if show_nondominated and "is_nondominated_3d" in df.columns:
        nd = df[df["is_nondominated_3d"] == True].copy()
        if not nd.empty:
            ax.scatter(
                pd.to_numeric(nd[x_col], errors="coerce").to_numpy(dtype=float),
                pd.to_numeric(nd[y_col], errors="coerce").to_numpy(dtype=float),
                pd.to_numeric(nd[z_col], errors="coerce").to_numpy(dtype=float),
                marker="^",
                s=80,
                label="Non-dominated solutions",
            )

    if show_knee and "is_knee_3d" in df.columns:
        knee = df[df["is_knee_3d"] == True].copy()
        if not knee.empty:
            ax.scatter(
                pd.to_numeric(knee[x_col], errors="coerce").to_numpy(dtype=float),
                pd.to_numeric(knee[y_col], errors="coerce").to_numpy(dtype=float),
                pd.to_numeric(knee[z_col], errors="coerce").to_numpy(dtype=float),
                marker="*",
                s=160,
                label="Knee-like solution",
            )

    if annotate and "model_id" in df.columns:
        for _, row in df.iterrows():
            ax.text(
                float(row[x_col]),
                float(row[y_col]),
                float(row[z_col]),
                str(row["model_id"]),
                fontsize=8,
            )

    ax.set_xlabel("Net present value")
    ax.set_ylabel("Operational net carbon stock change")
    ax.set_zlabel("Weighted adjacent conflict")
    ax.set_title(title)

    if invert_z_axis:
        ax.invert_zaxis()

    ax.legend(loc="best")
    fig.tight_layout()

    return fig, ax


def _safe_to_csv(df: pd.DataFrame, path: Path, index: bool = False) -> None:
    df_out = pd.DataFrame() if df is None else df.copy()
    df_out = df_out.where(pd.notnull(df_out), "")
    df_out.to_csv(path, index=index)


def _sanitize_filename(value: Any) -> str:
    import re

    value = str(value).strip().replace(" ", "_")
    value = re.sub(r"[^A-Za-z0-9_\-\.]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_") or "run"


def _save_multi_epsilon_results(
    front_df: pd.DataFrame,
    solution_records: List[Dict[str, Any]],
    results_dir: str = "treemun_results",
    run_name: Optional[str] = None,
    fig=None,
    save_plot: bool = True,
    plot_dpi: int = 300,
) -> Dict[str, Any]:
    base_dir = Path(results_dir)

    if run_name is None:
        run_name = f"multi_epsilon_3d_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    run_name = _sanitize_filename(run_name)
    run_dir = base_dir / run_name
    conflicts_dir = run_dir / "conflicts"

    run_dir.mkdir(parents=True, exist_ok=True)
    conflicts_dir.mkdir(parents=True, exist_ok=True)

    front_csv = run_dir / "multi_epsilon_front_3d.csv"
    _safe_to_csv(front_df, front_csv, index=False)

    plot_path = None
    if save_plot and fig is not None:
        plot_path = run_dir / "multi_epsilon_front_3d.png"
        fig.savefig(plot_path, dpi=plot_dpi, bbox_inches="tight")

    # Save conflicts per solved model.
    for rec in solution_records:
        row = rec.get("row", {})
        model_id = row.get("model_id", rec.get("model_id", "model"))
        label = _sanitize_filename(row.get("model_label", f"model_{model_id}"))
        conflicts = rec.get("conflicts", pd.DataFrame())
        _safe_to_csv(conflicts, conflicts_dir / f"{label}_conflicts.csv", index=False)

    summary_txt = run_dir / "multi_epsilon_front_3d_summary.txt"
    with open(summary_txt, "w", encoding="utf-8") as f:
        f.write("treemun-sim 3D multi-epsilon front summary\n")
        f.write("=" * 72 + "\n\n")
        f.write(f"n_models: {len(front_df)}\n")
        if "solved" in front_df.columns:
            f.write(f"n_solved: {int(front_df['solved'].sum())}\n")
        if "is_nondominated_3d" in front_df.columns:
            f.write(f"n_nondominated_3d: {int(front_df['is_nondominated_3d'].sum())}\n")
        f.write(f"front_csv: {front_csv}\n")
        if plot_path is not None:
            f.write(f"front_plot_png: {plot_path}\n")
        f.write("\nFront table\n")
        f.write("-" * 72 + "\n")
        f.write(front_df.to_string(index=False))
        f.write("\n")

    metadata = {
        "run_name": run_name,
        "run_dir": str(run_dir),
        "front_csv": str(front_csv),
        "summary_txt": str(summary_txt),
        "front_plot_png": str(plot_path) if plot_path is not None else None,
        "conflicts_dir": str(conflicts_dir),
    }

    metadata_path = run_dir / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"Results saved to: {run_dir}")

    return metadata


__all__ = [
    "build_multi_epsilon_front_3d",
    "plot_multi_epsilon_front_3d",
    "count_adjacent_final_harvest_conflicts",
]

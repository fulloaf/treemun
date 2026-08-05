"""Spatial adjacency and green-up extensions for Treemün Pyomo models."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Iterable, Mapping, Sequence

import pandas as pd


def _require_pyomo():
    try:
        import pyomo.environ as pyo
    except ImportError as exc:
        raise ImportError(
            "Spatial optimization requires Pyomo. Install "
            "`treemun-sim[optimization]`."
        ) from exc
    return pyo


def build_adjacency_edges(
    geometry_file: str | Path,
    *,
    stand_id_column: str = "stand_id",
    minimum_shared_boundary: float = 0.0,
) -> pd.DataFrame:
    """Build undirected polygon-adjacency edges and shared-boundary lengths."""
    from .spatial import _load_geometries

    geometries = _load_geometries(
        geometry_file, stand_id_column=stand_id_column
    )[[stand_id_column, "geometry"]].reset_index(drop=True)
    if geometries.crs is not None and getattr(geometries.crs, "is_geographic", False):
        raise ValueError(
            "A projected CRS is required to calculate shared-boundary lengths."
        )
    minimum_shared_boundary = float(minimum_shared_boundary)
    if minimum_shared_boundary < 0:
        raise ValueError("minimum_shared_boundary cannot be negative.")

    records: list[dict[str, object]] = []
    spatial_index = geometries.sindex
    for left_index, left_row in geometries.iterrows():
        candidate_indices = spatial_index.query(left_row.geometry, predicate="intersects")
        for right_index in candidate_indices:
            right_index = int(right_index)
            if right_index <= left_index:
                continue
            right_row = geometries.iloc[right_index]
            shared_boundary = left_row.geometry.boundary.intersection(
                right_row.geometry.boundary
            ).length
            if shared_boundary <= minimum_shared_boundary:
                continue
            records.append(
                {
                    "stand_id_a": str(left_row[stand_id_column]),
                    "stand_id_b": str(right_row[stand_id_column]),
                    "shared_boundary_length": float(shared_boundary),
                }
            )
    return pd.DataFrame.from_records(
        records,
        columns=["stand_id_a", "stand_id_b", "shared_boundary_length"],
    ).sort_values(["stand_id_a", "stand_id_b"], ignore_index=True)


def build_final_harvest_indicator(
    forest: Sequence[pd.DataFrame],
) -> dict[tuple[str, str, int], int]:
    """Return ``1`` for each stand-policy-period containing a final harvest."""
    indicator: dict[tuple[str, str, int], int] = {}
    for trajectory in forest:
        required = {"stand_id", "policy", "period", "operation"}
        missing = required - set(trajectory.columns)
        if missing:
            raise ValueError(f"Trajectory is missing columns: {sorted(missing)}")
        final_rows = trajectory.loc[trajectory["operation"].eq("final_harvest")]
        for row in final_rows.itertuples(index=False):
            indicator[(str(row.stand_id), str(row.policy), int(row.period))] = 1
    return indicator


def _normalize_edges(adjacency_edges: pd.DataFrame | Iterable[tuple]) -> list[tuple[str, str, float]]:
    if isinstance(adjacency_edges, pd.DataFrame):
        required = {"stand_id_a", "stand_id_b"}
        missing = required - set(adjacency_edges.columns)
        if missing:
            raise ValueError(f"Adjacency table is missing columns: {sorted(missing)}")
        weights = (
            adjacency_edges["shared_boundary_length"]
            if "shared_boundary_length" in adjacency_edges
            else pd.Series(1.0, index=adjacency_edges.index)
        )
        return [
            (str(a), str(b), float(weight))
            for a, b, weight in zip(
                adjacency_edges["stand_id_a"],
                adjacency_edges["stand_id_b"],
                weights,
            )
        ]
    normalized = []
    for edge in adjacency_edges:
        if len(edge) == 2:
            a, b = edge
            weight = 1.0
        elif len(edge) == 3:
            a, b, weight = edge
        else:
            raise ValueError(f"Adjacency edge must have two or three values: {edge}")
        normalized.append((str(a), str(b), float(weight)))
    return normalized


def _harvest_terms(model, indicator, stand_id: str, period: int):
    return [
        model.select_policy[stand, policy]
        for stand, policy in model.ALTERNATIVES
        if str(stand) == stand_id
        and indicator.get((str(stand), str(policy), int(period)), 0)
    ]


def add_spatial_conflict_measure(
    model,
    *,
    adjacency_edges: pd.DataFrame | Iterable[tuple],
    final_harvest_indicator: Mapping[tuple[str, str, int], int],
    greenup_window: int = 0,
    weight_by_shared_boundary: bool = False,
):
    """Add an exact green-up event-conflict measure without changing the objective.

    A green-up event conflict occurs when adjacent stands are assigned final
    harvests whose periods differ by no more than ``greenup_window``. The
    preferred expression is ``model.greenup_event_conflict_value``.
    ``model.spatial_conflict_value`` is retained as a compatibility alias.

    Parameters
    ----------
    greenup_window:
        Zero counts only simultaneous adjacent final harvests. Positive values
        count harvests that violate the corresponding green-up separation.
    weight_by_shared_boundary:
        When true, conflicts are weighted by shared-boundary length. Otherwise
        each stand-pair-period conflict contributes one unit.
    """
    extension_started = perf_counter()
    pyo = _require_pyomo()
    if hasattr(model, "spatial_conflict_value") or hasattr(
        model, "greenup_event_conflict_value"
    ):
        raise ValueError(
            "The model already contains a spatial_conflict_value component."
        )

    greenup_window = int(greenup_window)
    if greenup_window < 0:
        raise ValueError("greenup_window cannot be negative.")
    edges = _normalize_edges(adjacency_edges)

    conflict_keys: list[tuple[int, int, int]] = []
    terms_by_key: dict[tuple[int, int, int], tuple[list, list, float]] = {}
    periods = [int(period) for period in model.PERIODS]
    for edge_index, (stand_a, stand_b, shared_boundary) in enumerate(edges):
        for period_a in periods:
            left_terms = _harvest_terms(
                model, final_harvest_indicator, stand_a, period_a
            )
            if not left_terms:
                continue
            for period_b in periods:
                if abs(period_a - period_b) > greenup_window:
                    continue
                right_terms = _harvest_terms(
                    model, final_harvest_indicator, stand_b, period_b
                )
                if not right_terms:
                    continue
                key = (edge_index, period_a, period_b)
                conflict_keys.append(key)
                terms_by_key[key] = (left_terms, right_terms, shared_boundary)

    model.SPATIAL_CONFLICT_INDEX = pyo.Set(
        dimen=3, initialize=conflict_keys, ordered=True
    )
    model.spatial_conflict = pyo.Var(
        model.SPATIAL_CONFLICT_INDEX, domain=pyo.Binary
    )

    def conflict_lower_rule(pyomo_model, edge_index, period_a, period_b):
        left_terms, right_terms, _ = terms_by_key[
            (edge_index, period_a, period_b)
        ]
        return pyomo_model.spatial_conflict[
            edge_index, period_a, period_b
        ] >= sum(left_terms) + sum(right_terms) - 1

    def conflict_left_upper_rule(pyomo_model, edge_index, period_a, period_b):
        left_terms, _, _ = terms_by_key[(edge_index, period_a, period_b)]
        return pyomo_model.spatial_conflict[
            edge_index, period_a, period_b
        ] <= sum(left_terms)

    def conflict_right_upper_rule(pyomo_model, edge_index, period_a, period_b):
        _, right_terms, _ = terms_by_key[(edge_index, period_a, period_b)]
        return pyomo_model.spatial_conflict[
            edge_index, period_a, period_b
        ] <= sum(right_terms)

    model.spatial_conflict_lower = pyo.Constraint(
        model.SPATIAL_CONFLICT_INDEX, rule=conflict_lower_rule
    )
    model.spatial_conflict_left_upper = pyo.Constraint(
        model.SPATIAL_CONFLICT_INDEX, rule=conflict_left_upper_rule
    )
    model.spatial_conflict_right_upper = pyo.Constraint(
        model.SPATIAL_CONFLICT_INDEX, rule=conflict_right_upper_rule
    )
    model.greenup_event_conflict_value = pyo.Expression(
        expr=sum(
            (
                terms_by_key[key][2]
                if weight_by_shared_boundary
                else 1.0
            )
            * model.spatial_conflict[key]
            for key in model.SPATIAL_CONFLICT_INDEX
        )
    )
    # Compatibility alias retained for existing notebooks and user code.
    model.spatial_conflict_value = pyo.Expression(
        expr=model.greenup_event_conflict_value
    )
    model._treemun_greenup_event_conflict_metadata = {
        "greenup_window": greenup_window,
        "weight_by_shared_boundary": bool(weight_by_shared_boundary),
        "number_of_potential_greenup_event_conflicts": len(conflict_keys),
    }
    model._treemun_spatial_conflict_metadata = (
        model._treemun_greenup_event_conflict_metadata
    )
    _record_spatial_extension_time(model, extension_started)
    return model


def _replace_objective_with_penalty(model, penalty_expression, component_name: str):
    pyo = _require_pyomo()
    active_objectives = list(model.component_data_objects(pyo.Objective, active=True))
    if len(active_objectives) != 1:
        raise ValueError("Model must have exactly one active objective.")
    old_objective = active_objectives[0]
    expression = old_objective.expr - penalty_expression
    sense = old_objective.sense
    old_objective.deactivate()
    setattr(model, component_name, pyo.Objective(expr=expression, sense=sense))


def _record_spatial_extension_time(model, started: float) -> None:
    if hasattr(model, "_treemun_metadata"):
        model._treemun_metadata["spatial_extension_build_time_seconds"] = (
            float(
                model._treemun_metadata.get(
                    "spatial_extension_build_time_seconds", 0.0
                )
            )
            + float(perf_counter() - started)
        )


def add_final_harvest_adjacency(
    model,
    *,
    adjacency_edges: pd.DataFrame | Iterable[tuple],
    final_harvest_indicator: Mapping[tuple[str, str, int], int],
    mode: str = "hard",
    penalty: float = 1.0,
    weight_by_shared_boundary: bool = False,
):
    """Prevent or penalize simultaneous final harvests in adjacent stands."""
    extension_started = perf_counter()
    pyo = _require_pyomo()
    mode = str(mode).lower()
    if mode not in {"hard", "soft"}:
        raise ValueError("mode must be 'hard' or 'soft'.")
    edges = _normalize_edges(adjacency_edges)
    indexed_conflicts: list[tuple[int, int]] = []
    terms_by_index: dict[tuple[int, int], tuple[list, list, float]] = {}
    for edge_index, (stand_a, stand_b, weight) in enumerate(edges):
        for period in model.PERIODS:
            left_terms = _harvest_terms(
                model, final_harvest_indicator, stand_a, int(period)
            )
            right_terms = _harvest_terms(
                model, final_harvest_indicator, stand_b, int(period)
            )
            if left_terms and right_terms:
                key = (edge_index, int(period))
                indexed_conflicts.append(key)
                terms_by_index[key] = (left_terms, right_terms, weight)

    model.same_period_adjacency_index = pyo.Set(
        dimen=2, initialize=indexed_conflicts
    )
    if mode == "hard":
        def hard_rule(pyomo_model, edge_index, period):
            left_terms, right_terms, _ = terms_by_index[(edge_index, period)]
            return sum(left_terms) + sum(right_terms) <= 1

        model.same_period_adjacency = pyo.Constraint(
            model.same_period_adjacency_index, rule=hard_rule
        )
    else:
        model.same_period_adjacency_conflict = pyo.Var(
            model.same_period_adjacency_index, domain=pyo.Binary
        )

        def soft_rule(pyomo_model, edge_index, period):
            left_terms, right_terms, _ = terms_by_index[(edge_index, period)]
            return pyomo_model.same_period_adjacency_conflict[
                edge_index, period
            ] >= sum(left_terms) + sum(right_terms) - 1

        model.same_period_adjacency_link = pyo.Constraint(
            model.same_period_adjacency_index, rule=soft_rule
        )
        penalty_expression = float(penalty) * sum(
            (terms_by_index[key][2] if weight_by_shared_boundary else 1.0)
            * model.same_period_adjacency_conflict[key]
            for key in model.same_period_adjacency_index
        )
        _replace_objective_with_penalty(
            model, penalty_expression, "objective_with_adjacency_penalty"
        )
    _record_spatial_extension_time(model, extension_started)
    return model


def add_greenup_adjacency(
    model,
    *,
    adjacency_edges: pd.DataFrame | Iterable[tuple],
    final_harvest_indicator: Mapping[tuple[str, str, int], int],
    greenup_window: int,
    mode: str = "hard",
    penalty: float = 1.0,
    weight_by_shared_boundary: bool = False,
):
    """Prevent or penalize adjacent final harvests within a green-up window."""
    extension_started = perf_counter()
    pyo = _require_pyomo()
    greenup_window = int(greenup_window)
    if greenup_window < 0:
        raise ValueError("greenup_window cannot be negative.")
    mode = str(mode).lower()
    if mode not in {"hard", "soft"}:
        raise ValueError("mode must be 'hard' or 'soft'.")
    edges = _normalize_edges(adjacency_edges)

    conflict_pairs: list[tuple[int, int, int, int]] = []
    terms_by_index: dict[tuple[int, int, int, int], tuple[list, list, float]] = {}
    periods = [int(period) for period in model.PERIODS]
    for edge_index, (stand_a, stand_b, weight) in enumerate(edges):
        for period_a in periods:
            left_terms = _harvest_terms(
                model, final_harvest_indicator, stand_a, period_a
            )
            if not left_terms:
                continue
            for period_b in periods:
                if abs(period_a - period_b) > greenup_window:
                    continue
                right_terms = _harvest_terms(
                    model, final_harvest_indicator, stand_b, period_b
                )
                if not right_terms:
                    continue
                key = (edge_index, period_a, period_b, greenup_window)
                conflict_pairs.append(key)
                terms_by_index[key] = (left_terms, right_terms, weight)

    model.greenup_adjacency_index = pyo.Set(dimen=4, initialize=conflict_pairs)
    if mode == "hard":
        def hard_rule(pyomo_model, edge_index, period_a, period_b, window):
            left_terms, right_terms, _ = terms_by_index[
                (edge_index, period_a, period_b, window)
            ]
            return sum(left_terms) + sum(right_terms) <= 1

        model.greenup_adjacency = pyo.Constraint(
            model.greenup_adjacency_index, rule=hard_rule
        )
    else:
        model.greenup_adjacency_conflict = pyo.Var(
            model.greenup_adjacency_index, domain=pyo.Binary
        )

        def soft_rule(pyomo_model, edge_index, period_a, period_b, window):
            key = (edge_index, period_a, period_b, window)
            left_terms, right_terms, _ = terms_by_index[key]
            return pyomo_model.greenup_adjacency_conflict[key] >= (
                sum(left_terms) + sum(right_terms) - 1
            )

        model.greenup_adjacency_link = pyo.Constraint(
            model.greenup_adjacency_index, rule=soft_rule
        )
        penalty_expression = float(penalty) * sum(
            (terms_by_index[key][2] if weight_by_shared_boundary else 1.0)
            * model.greenup_adjacency_conflict[key]
            for key in model.greenup_adjacency_index
        )
        _replace_objective_with_penalty(
            model, penalty_expression, "objective_with_greenup_penalty"
        )
    _record_spatial_extension_time(model, extension_started)
    return model


def count_greenup_event_conflicts(
    *,
    selected_policies: pd.DataFrame,
    forest: Sequence[pd.DataFrame],
    adjacency_edges: pd.DataFrame | Iterable[tuple],
    greenup_window: int,
) -> pd.DataFrame:
    """List realized green-up event conflicts in a selected plan."""
    selected = pd.DataFrame(selected_policies)
    required = {"stand_id", "policy"}
    missing = required - set(selected.columns)
    if missing:
        raise ValueError(f"selected_policies is missing columns: {sorted(missing)}")
    indicator = build_final_harvest_indicator(forest)
    selected_map = dict(zip(selected["stand_id"].astype(str), selected["policy"].astype(str)))
    periods_by_stand: dict[str, list[int]] = {}
    for stand_id, policy in selected_map.items():
        periods_by_stand[stand_id] = sorted(
            period
            for (candidate_stand, candidate_policy, period), value in indicator.items()
            if value and candidate_stand == stand_id and candidate_policy == policy
        )

    records: list[dict[str, object]] = []
    for stand_a, stand_b, weight in _normalize_edges(adjacency_edges):
        for period_a in periods_by_stand.get(stand_a, []):
            for period_b in periods_by_stand.get(stand_b, []):
                distance = abs(period_a - period_b)
                if distance <= int(greenup_window):
                    records.append(
                        {
                            "stand_id_a": stand_a,
                            "stand_id_b": stand_b,
                            "period_a": period_a,
                            "period_b": period_b,
                            "period_distance": distance,
                            "shared_boundary_length": weight,
                        }
                    )
    return pd.DataFrame.from_records(records)


# Compatibility aliases retained for Treemün 2.0 draft notebooks.
add_greenup_event_conflict_measure = add_spatial_conflict_measure
count_greenup_adjacency_conflicts = count_greenup_event_conflicts

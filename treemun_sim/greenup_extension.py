
"""
Green-up adjacency extension for Treemün.

This module adds optional green-up style adjacency constraints or penalties
to an existing Treemün Pyomo model.

greenup_window = 0:
    controls simultaneous final harvests in adjacent stands.

greenup_window = 1:
    controls final harvests in adjacent stands occurring in the same or
    consecutive planning periods.

The soft penalty mode is recommended for commercial plantation planning,
because hard green-up constraints may easily become infeasible.
"""

from __future__ import annotations

import pandas as pd

from pyomo.environ import (
    Set,
    Var,
    Constraint,
    Expression,
    Objective,
    NonNegativeReals,
    maximize,
    minimize,
    value,
)


def _delete_component_if_exists(model, component_name):
    if hasattr(model, component_name):
        model.del_component(getattr(model, component_name))


def _get_periods_from_model(model, periods=None):
    if periods is not None:
        return sorted([int(t) for t in periods])

    if hasattr(model, "T"):
        return sorted([int(t) for t in list(model.T)])

    raise ValueError(
        "Could not infer periods. Pass periods explicitly or use a model with model.T."
    )


def _prepare_adjacency_edges(
    adjacency_edges,
    stand_1_col="stand_id_1",
    stand_2_col="stand_id_2",
    weight_col="shared_boundary_m",
):
    if isinstance(adjacency_edges, pd.DataFrame):
        edges = adjacency_edges.copy()
    else:
        edges = pd.DataFrame(adjacency_edges)

    required = [stand_1_col, stand_2_col]

    for col in required:
        if col not in edges.columns:
            raise ValueError(f"Column '{col}' was not found in adjacency_edges.")

    if weight_col is None or weight_col not in edges.columns:
        edges["_greenup_weight"] = 1.0
        weight_col = "_greenup_weight"

    edges[stand_1_col] = edges[stand_1_col].astype(str)
    edges[stand_2_col] = edges[stand_2_col].astype(str)
    edges[weight_col] = pd.to_numeric(edges[weight_col], errors="coerce").fillna(1.0)

    # Remove self-loops
    edges = edges[edges[stand_1_col] != edges[stand_2_col]].copy()

    # Create canonical unordered edge representation
    edges["_s"] = edges[[stand_1_col, stand_2_col]].min(axis=1)
    edges["_r"] = edges[[stand_1_col, stand_2_col]].max(axis=1)

    edges = (
        edges.groupby(["_s", "_r"], as_index=False)
        .agg(weight=(weight_col, "sum"))
    )

    return edges


def _indicator_lookup(
    final_harvest_indicator,
    period,
    species_candidates,
    policy_name,
    stand_id,
):
    """
    Robust lookup for final_harvest_indicator.

    Expected main key format:
        (period, species_key, policy_name, stand_id)

    Example:
        (10, "Pinus", "Pino_12", "45")
    """

    period_candidates = [int(period), str(period)]
    policy_candidates = [policy_name, str(policy_name)]
    stand_candidates = [stand_id, str(stand_id)]

    try:
        stand_candidates.append(int(stand_id))
    except Exception:
        pass

    for tt in period_candidates:
        for sp in species_candidates:
            for pp in policy_candidates:
                for ss in stand_candidates:
                    key = (tt, sp, pp, ss)

                    if key in final_harvest_indicator:
                        try:
                            return int(final_harvest_indicator[key])
                        except Exception:
                            return 0

    return 0


def _build_stand_period_terms(
    model,
    final_harvest_indicator,
    stand_ids,
    periods,
):
    """
    Builds linear expressions y_{s,t} as a list of selected-policy variables.

    y_{s,t} = sum_j h_{s,j,t} x_{s,j}

    where h_{s,j,t}=1 if policy j performs a final harvest in period t.
    """

    stand_ids = set(str(s) for s in stand_ids)

    terms_by_stand_period = {
        (str(s), int(t)): []
        for s in stand_ids
        for t in periods
    }

    # Pine variables
    if hasattr(model, "x_pine"):
        for i, j in model.x_pine:
            s = str(i)

            if s not in stand_ids:
                continue

            for t in periods:
                h = _indicator_lookup(
                    final_harvest_indicator=final_harvest_indicator,
                    period=t,
                    species_candidates=["Pinus", "Pino", "pine"],
                    policy_name=j,
                    stand_id=s,
                )

                if h == 1:
                    terms_by_stand_period[(s, int(t))].append(model.x_pine[i, j])

    # Eucalyptus variables
    if hasattr(model, "x_eucalyptus"):
        for i, j in model.x_eucalyptus:
            s = str(i)

            if s not in stand_ids:
                continue

            for t in periods:
                h = _indicator_lookup(
                    final_harvest_indicator=final_harvest_indicator,
                    period=t,
                    species_candidates=[
                        "Eucapyltus",
                        "Eucalyptus",
                        "Eucaliptus",
                        "eucalyptus",
                    ],
                    policy_name=j,
                    stand_id=s,
                )

                if h == 1:
                    terms_by_stand_period[(s, int(t))].append(model.x_eucalyptus[i, j])

    return terms_by_stand_period


def _sum_terms(terms):
    expr = 0

    for term in terms:
        expr += term

    return expr


def _get_active_objective(model):
    active_objectives = list(model.component_data_objects(Objective, active=True))

    if len(active_objectives) == 0:
        raise ValueError("No active objective was found in the model.")

    if len(active_objectives) > 1:
        raise ValueError(
            "More than one active objective was found. "
            "Please deactivate extra objectives before adding green-up penalty."
        )

    return active_objectives[0]


def add_greenup_adjacency(
    model,
    final_harvest_indicator,
    adjacency_edges,
    greenup_window=1,
    mode="penalty",
    phi=0.0,
    adjacency_weight_col="shared_boundary_m",
    adjacency_scale=None,
    base_objective_scale=None,
    base_objective_is_normalized=False,
    periods=None,
    stand_1_col="stand_id_1",
    stand_2_col="stand_id_2",
    component_suffix="greenup_ext",
):
    """
    Add green-up adjacency constraints or penalties to a Treemün model.

    Parameters
    ----------
    model:
        Existing Treemün Pyomo model.

    final_harvest_indicator:
        Dictionary with keys:
            (period, species_key, policy_name, stand_id) -> 0/1

    adjacency_edges:
        DataFrame or list-like object with at least:
            stand_id_1, stand_id_2
        and optionally:
            shared_boundary_m

    greenup_window:
        Integer g >= 0.
        g=0 controls same-period adjacent final harvests.
        g=1 controls same-period and consecutive-period adjacent final harvests.

    mode:
        "hard" or "penalty".

        hard:
            y_{s,t} + y_{r,tau} <= 1
            for |t - tau| <= g.

        penalty:
            z_{s,r,t,tau} = 1 if both adjacent stands are finally harvested
            within the green-up window, and penalizes this in the objective.

    phi:
        Penalty weight. Used only when mode="penalty".

    adjacency_weight_col:
        Edge weight column. Usually shared boundary length.

    adjacency_scale:
        Optional scale for normalizing adjacency penalty.
        If None, the maximum possible weighted green-up conflict is used.

    base_objective_scale:
        Positive scale for normalizing the original objective when it is not
        already normalized.

    base_objective_is_normalized:
        True if the active objective is already normalized, e.g. weighted
        NPV-carbon objective in Treemün.

    Returns
    -------
    model:
        Modified Pyomo model.
    """

    g = int(greenup_window)

    if g < 0:
        raise ValueError("greenup_window must be >= 0.")

    mode = str(mode).lower()

    if mode in {"soft", "penalty", "penalty_greenup", "soft_greenup"}:
        mode = "penalty"

    elif mode in {"hard", "hard_greenup", "constraint", "constraints"}:
        mode = "hard"

    else:
        raise ValueError("mode must be 'penalty' or 'hard'.")

    # Delete previous components with the same suffix
    components_to_delete = [
        f"greenup_pairs_{component_suffix}",
        f"greenup_conflict_{component_suffix}",
        f"greenup_conflict_lb_{component_suffix}",
        f"greenup_conflict_ub1_{component_suffix}",
        f"greenup_conflict_ub2_{component_suffix}",
        f"greenup_hard_constraint_{component_suffix}",
        f"greenup_adjacency_value_{component_suffix}",
        f"greenup_adjacency_normalized_{component_suffix}",
        f"objective_with_greenup_{component_suffix}",
    ]

    for component_name in components_to_delete:
        _delete_component_if_exists(model, component_name)

    periods = _get_periods_from_model(model, periods=periods)

    edges = _prepare_adjacency_edges(
        adjacency_edges=adjacency_edges,
        stand_1_col=stand_1_col,
        stand_2_col=stand_2_col,
        weight_col=adjacency_weight_col,
    )

    stand_ids = sorted(set(edges["_s"].astype(str)) | set(edges["_r"].astype(str)))

    terms_by_stand_period = _build_stand_period_terms(
        model=model,
        final_harvest_indicator=final_harvest_indicator,
        stand_ids=stand_ids,
        periods=periods,
    )

    triples = []
    weights = {}

    for _, row in edges.iterrows():
        s = str(row["_s"])
        r = str(row["_r"])
        w = float(row["weight"])

        for t in periods:
            for tau in periods:
                if abs(int(t) - int(tau)) <= g:
                    # Add only meaningful potential conflicts
                    if (
                        len(terms_by_stand_period[(s, int(t))]) > 0
                        and len(terms_by_stand_period[(r, int(tau))]) > 0
                    ):
                        key = (s, r, int(t), int(tau))
                        triples.append(key)
                        weights[key] = w

    setattr(
        model,
        f"greenup_pairs_{component_suffix}",
        Set(dimen=4, initialize=triples),
    )

    greenup_pairs = getattr(model, f"greenup_pairs_{component_suffix}")

    if mode == "hard":

        def hard_rule(m, s, r, t, tau):
            y_s_t = _sum_terms(terms_by_stand_period[(str(s), int(t))])
            y_r_tau = _sum_terms(terms_by_stand_period[(str(r), int(tau))])

            return y_s_t + y_r_tau <= 1

        setattr(
            model,
            f"greenup_hard_constraint_{component_suffix}",
            Constraint(greenup_pairs, rule=hard_rule),
        )

        model.greenup_window = g
        model.greenup_mode = mode

        return model

    # Soft penalty mode
    setattr(
        model,
        f"greenup_conflict_{component_suffix}",
        Var(greenup_pairs, domain=NonNegativeReals, bounds=(0.0, 1.0)),
    )

    z = getattr(model, f"greenup_conflict_{component_suffix}")

    def lb_rule(m, s, r, t, tau):
        y_s_t = _sum_terms(terms_by_stand_period[(str(s), int(t))])
        y_r_tau = _sum_terms(terms_by_stand_period[(str(r), int(tau))])

        return z[s, r, t, tau] >= y_s_t + y_r_tau - 1

    def ub1_rule(m, s, r, t, tau):
        y_s_t = _sum_terms(terms_by_stand_period[(str(s), int(t))])

        return z[s, r, t, tau] <= y_s_t

    def ub2_rule(m, s, r, t, tau):
        y_r_tau = _sum_terms(terms_by_stand_period[(str(r), int(tau))])

        return z[s, r, t, tau] <= y_r_tau

    setattr(
        model,
        f"greenup_conflict_lb_{component_suffix}",
        Constraint(greenup_pairs, rule=lb_rule),
    )

    setattr(
        model,
        f"greenup_conflict_ub1_{component_suffix}",
        Constraint(greenup_pairs, rule=ub1_rule),
    )

    setattr(
        model,
        f"greenup_conflict_ub2_{component_suffix}",
        Constraint(greenup_pairs, rule=ub2_rule),
    )

    if adjacency_scale is None:
        adjacency_scale = sum(float(weights[key]) for key in triples)

    adjacency_scale = max(float(adjacency_scale), 1.0)

    setattr(
        model,
        f"greenup_adjacency_value_{component_suffix}",
        Expression(
            expr=sum(
                float(weights[(s, r, t, tau)]) * z[s, r, t, tau]
                for (s, r, t, tau) in triples
            )
        ),
    )

    greenup_adjacency_value = getattr(
        model,
        f"greenup_adjacency_value_{component_suffix}",
    )

    setattr(
        model,
        f"greenup_adjacency_normalized_{component_suffix}",
        Expression(
            expr=greenup_adjacency_value / adjacency_scale
        ),
    )

    greenup_adjacency_normalized = getattr(
        model,
        f"greenup_adjacency_normalized_{component_suffix}",
    )

    active_obj = _get_active_objective(model)
    base_expr = active_obj.expr
    base_sense = active_obj.sense

    if base_objective_is_normalized:
        normalized_base_expr = base_expr
    else:
        if base_objective_scale is None:
            base_objective_scale = 1.0

        base_objective_scale = max(abs(float(base_objective_scale)), 1.0)
        normalized_base_expr = base_expr / base_objective_scale

    active_obj.deactivate()

    if base_sense == maximize:
        new_expr = normalized_base_expr - float(phi) * greenup_adjacency_normalized
        new_sense = maximize
    elif base_sense == minimize:
        new_expr = normalized_base_expr + float(phi) * greenup_adjacency_normalized
        new_sense = minimize
    else:
        raise ValueError("Objective sense must be maximize or minimize.")

    setattr(
        model,
        f"objective_with_greenup_{component_suffix}",
        Objective(expr=new_expr, sense=new_sense),
    )

    # Friendly aliases
    model.greenup_window = g
    model.greenup_mode = mode
    model.greenup_phi = float(phi)
    model.greenup_adjacency_scale = float(adjacency_scale)
    # Friendly aliases.
    # Use object.__setattr__ to avoid registering the same Pyomo component twice.
    object.__setattr__(model, "greenup_adjacency_value", greenup_adjacency_value)
    object.__setattr__(model, "greenup_adjacency_normalized", greenup_adjacency_normalized)

    return model


def extract_selected_policies_from_model(model):
    selected = {}

    if hasattr(model, "x_pine"):
        for i, j in model.x_pine:
            xval = value(model.x_pine[i, j], exception=False)

            if xval is not None and xval > 0.5:
                selected[str(i)] = str(j)

    if hasattr(model, "x_eucalyptus"):
        for i, j in model.x_eucalyptus:
            xval = value(model.x_eucalyptus[i, j], exception=False)

            if xval is not None and xval > 0.5:
                selected[str(i)] = str(j)

    return selected


def species_key_candidates_from_policy(policy_name):
    p = str(policy_name).lower()

    if "pino" in p or "pinus" in p:
        return ["Pinus", "Pino", "pine"]

    if "euca" in p or "eucalyptus" in p:
        return ["Eucapyltus", "Eucalyptus", "Eucaliptus", "eucalyptus"]

    return ["Pinus", "Pino", "Eucapyltus", "Eucalyptus"]


def final_harvest_periods_for_selected_policy(
    stand_id,
    policy_name,
    final_harvest_indicator,
    periods,
):
    species_candidates = species_key_candidates_from_policy(policy_name)

    out = []

    for t in periods:
        h = _indicator_lookup(
            final_harvest_indicator=final_harvest_indicator,
            period=t,
            species_candidates=species_candidates,
            policy_name=policy_name,
            stand_id=stand_id,
        )

        if h == 1:
            out.append(int(t))

    return out


def count_greenup_adjacency_conflicts(
    model,
    adjacency_edges,
    final_harvest_indicator,
    greenup_window=1,
    periods=None,
    adjacency_weight_col="shared_boundary_m",
    stand_1_col="stand_id_1",
    stand_2_col="stand_id_2",
):
    """
    External diagnostic for green-up adjacency conflicts in a solved model.

    Returns
    -------
    n_conflicts:
        Number of edge-period-pair conflicts.

    weighted_conflicts:
        Sum of edge weights involved in green-up conflicts.

    conflicts_df:
        Detailed DataFrame with one row per conflict.
    """

    g = int(greenup_window)

    if g < 0:
        raise ValueError("greenup_window must be >= 0.")

    periods = _get_periods_from_model(model, periods=periods)

    edges = _prepare_adjacency_edges(
        adjacency_edges=adjacency_edges,
        stand_1_col=stand_1_col,
        stand_2_col=stand_2_col,
        weight_col=adjacency_weight_col,
    )

    selected = extract_selected_policies_from_model(model)

    final_periods = {}

    for stand_id, policy_name in selected.items():
        final_periods[str(stand_id)] = final_harvest_periods_for_selected_policy(
            stand_id=str(stand_id),
            policy_name=str(policy_name),
            final_harvest_indicator=final_harvest_indicator,
            periods=periods,
        )

    rows = []

    for _, row in edges.iterrows():
        s = str(row["_s"])
        r = str(row["_r"])
        w = float(row["weight"])

        policy_s = selected.get(s)
        policy_r = selected.get(r)

        if policy_s is None or policy_r is None:
            continue

        for t in final_periods.get(s, []):
            for tau in final_periods.get(r, []):
                if abs(int(t) - int(tau)) <= g:
                    rows.append(
                        {
                            "stand_id_1": s,
                            "stand_id_2": r,
                            "period_1": int(t),
                            "period_2": int(tau),
                            "period_gap": abs(int(t) - int(tau)),
                            "shared_boundary_m": w,
                            "policy_1": policy_s,
                            "policy_2": policy_r,
                        }
                    )

    conflicts_df = pd.DataFrame(rows)

    n_conflicts = len(conflicts_df)

    if n_conflicts > 0:
        weighted_conflicts = float(conflicts_df["shared_boundary_m"].sum())
    else:
        weighted_conflicts = 0.0

    return n_conflicts, weighted_conflicts, conflicts_df

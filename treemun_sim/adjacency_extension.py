"""
Adjacency-aware extensions for treemun-sim optimization models.

This module adds optional spatial adjacency constraints or penalties to an
already-created Pyomo model. It does not modify the base optimization.py file.

v1.4.0 scaled update
--------------------
The soft adjacency penalty can now be combined with either:

1. an already-normalized active objective; or
2. an unnormalized active objective, by passing ``base_objective_scale``.

This avoids mixing a large NPV value, e.g. USD, with a normalized spatial
penalty. The recommended form is:

    scaled_base_objective - phi * normalized_adjacency_penalty

where both terms are dimensionless and comparable.
"""

from pyomo.environ import (
    Set,
    Param,
    Var,
    Constraint,
    Expression,
    Objective,
    NonNegativeReals,
    maximize,
)


def _delete_component_if_exists(model, name):
    """Delete a Pyomo component if it already exists."""
    if hasattr(model, name):
        model.del_component(getattr(model, name))


def _normalize_adjacency_edges_and_weights(
    adjacency_edges,
    valid_stands,
    adjacency_weight_col=None,
):
    """
    Normalize adjacency edges and optional weights.

    adjacency_edges can be:
    - a pandas DataFrame with columns stand_id_1 and stand_id_2;
    - a list of tuples: [(s, r), ...].
    """
    if adjacency_edges is None:
        return [], {}

    valid_stands = {str(s) for s in valid_stands}
    weights = {}

    if hasattr(adjacency_edges, "columns"):
        if "stand_id_1" not in adjacency_edges.columns or "stand_id_2" not in adjacency_edges.columns:
            raise ValueError(
                "adjacency_edges DataFrame must contain columns "
                "'stand_id_1' and 'stand_id_2'."
            )

        if adjacency_weight_col is None:
            for candidate in [
                "shared_boundary_m",
                "shared_boundary",
                "shared_boundary_length",
                "weight",
                "w_sr",
            ]:
                if candidate in adjacency_edges.columns:
                    adjacency_weight_col = candidate
                    break

        for row in adjacency_edges.to_dict("records"):
            s = str(row["stand_id_1"])
            r = str(row["stand_id_2"])

            if s == r:
                continue

            if s not in valid_stands or r not in valid_stands:
                continue

            edge = tuple(sorted((s, r)))
            weight = 1.0

            if adjacency_weight_col is not None and adjacency_weight_col in row:
                try:
                    weight = float(row[adjacency_weight_col])
                except (TypeError, ValueError):
                    weight = 1.0

            weights[edge] = max(weight, 0.0)

    else:
        for edge_like in adjacency_edges:
            if len(edge_like) < 2:
                raise ValueError(f"Invalid adjacency edge: {edge_like!r}")

            s = str(edge_like[0])
            r = str(edge_like[1])

            if s == r:
                continue

            if s not in valid_stands or r not in valid_stands:
                continue

            edge = tuple(sorted((s, r)))
            weights[edge] = 1.0

    clean_edges = sorted(weights.keys())
    return clean_edges, weights


def _get_final_harvest_indicator(
    final_harvest_indicator,
    t,
    species,
    policy,
    stand_original,
    stand_str,
):
    """
    Robust lookup for final harvest indicator.
    Tries both original and string versions of stand/policy.
    """
    candidate_species = [species]

    # Robustness for the current treemun-sim spelling and the standard spelling.
    if species == "Eucapyltus":
        candidate_species.append("Eucalyptus")
    elif species == "Eucalyptus":
        candidate_species.append("Eucapyltus")

    candidate_keys = []
    for species_key in candidate_species:
        candidate_keys.extend(
            [
                (int(t), species_key, policy, stand_original),
                (int(t), species_key, policy, stand_str),
                (int(t), species_key, str(policy), stand_original),
                (int(t), species_key, str(policy), stand_str),
            ]
        )

    for key in candidate_keys:
        if key in final_harvest_indicator:
            return float(final_harvest_indicator[key])

    return 0.0


def _active_objective(model):
    """Return the only active objective or raise a clear error."""
    active_objectives = list(model.component_objects(Objective, active=True))

    if len(active_objectives) != 1:
        raise ValueError(
            f"Expected exactly one active objective, found {len(active_objectives)}."
        )

    return active_objectives[0]


def add_final_harvest_adjacency(
    model,
    final_harvest_indicator,
    adjacency_edges,
    mode="hard_final_harvest",
    phi=0.0,
    adjacency_weight_col=None,
    adjacency_scale=None,
    base_objective_scale=None,
    base_objective_is_normalized=False,
):
    """
    Add adjacency-aware constraints or penalties to an existing Pyomo model.

    Parameters
    ----------
    model : pyomo.environ.ConcreteModel
        Treemun optimization model already created by
        forest_management_optimization_model().
    final_harvest_indicator : dict
        Dictionary with keys (period, species, policy, stand_id).
        Value 1 indicates that the selected policy implies final harvest
        in that period. Thinning should not be flagged here.
    adjacency_edges : list or pandas.DataFrame
        Spatial adjacency edges. If DataFrame, it must contain columns
        stand_id_1 and stand_id_2. Optional edge weights can be read from
        shared_boundary_m or another selected column.
    mode : str
        "hard_final_harvest" or "penalty_final_harvest".
    phi : float
        Spatial penalty weight. Used only when mode="penalty_final_harvest".
    adjacency_weight_col : str or None
        Column name for edge weights, e.g. "shared_boundary_m".
    adjacency_scale : float or None
        Optional scale for normalizing the adjacency penalty. If None, it is
        computed as total shared-boundary weight times the number of periods.
    base_objective_scale : float or None
        Scale for the active base objective when it is not already normalized.
        For NPV-only models, use a positive value such as the optimal NPV from
        the base NPV run or an upper-bound/ideal NPV scale.
    base_objective_is_normalized : bool
        If True, the active base objective is assumed to already be dimensionless
        and comparable to the normalized adjacency term. If False,
        base_objective_scale is required for penalty mode.

    Returns
    -------
    model : pyomo.environ.ConcreteModel
        Same model, modified in-place.
    """

    mode = str(mode).lower()

    if mode not in {"hard_final_harvest", "penalty_final_harvest"}:
        raise ValueError(
            "mode must be 'hard_final_harvest' or 'penalty_final_harvest'."
        )

    phi = float(phi)
    if phi < 0.0:
        raise ValueError("phi must be non-negative.")

    if final_harvest_indicator is None:
        raise ValueError("final_harvest_indicator is required.")

    # Maps from string id to original Pyomo set id.
    pine_id_map = {str(s): s for s in model.I_pino}
    euca_id_map = {str(s): s for s in model.I_euca}

    all_model_stands = set(pine_id_map.keys()) | set(euca_id_map.keys())

    clean_edges, edge_weights = _normalize_adjacency_edges_and_weights(
        adjacency_edges=adjacency_edges,
        valid_stands=all_model_stands,
        adjacency_weight_col=adjacency_weight_col,
    )

    if len(clean_edges) == 0:
        raise ValueError(
            "No valid adjacency edges remain after matching edge stand IDs "
            "with model stand IDs. Check id_rodal consistency."
        )

    # Remove old adjacency components if the function was already called.
    components_to_delete = [
        "adjacency_edges_ext",
        "adjacency_weight_ext",
        "no_adjacent_final_harvest_ext",
        "adjacent_final_harvest_ext",
        "adjacent_final_harvest_lb_ext",
        "adjacency_penalty_value_ext",
        "adjacency_scale_ext",
        "adjacency_phi_ext",
        "base_objective_before_adjacency_ext",
        "base_objective_scale_ext",
        "scaled_base_objective_ext",
        "objective_with_adjacency_ext",
    ]

    for name in components_to_delete:
        _delete_component_if_exists(model, name)

    model.adjacency_edges_ext = Set(dimen=2, initialize=clean_edges)

    def adjacency_weight_init(model, s, r):
        return float(edge_weights.get(tuple(sorted((str(s), str(r)))), 1.0))

    model.adjacency_weight_ext = Param(
        model.adjacency_edges_ext,
        initialize=adjacency_weight_init,
        within=NonNegativeReals,
        default=1.0,
    )

    def final_harvest_expr(model, stand_id_str, t):
        """
        Expression equal to 1 if stand_id_str is finally harvested in period t.
        """
        stand_id_str = str(stand_id_str)

        if stand_id_str in pine_id_map:
            i = pine_id_map[stand_id_str]
            return sum(
                _get_final_harvest_indicator(
                    final_harvest_indicator,
                    t,
                    "Pinus",
                    j,
                    i,
                    stand_id_str,
                )
                * model.x_pine[i, j]
                for j in model.J_pino
                if (i, j) in model.x_pine
            )

        if stand_id_str in euca_id_map:
            i = euca_id_map[stand_id_str]
            return sum(
                _get_final_harvest_indicator(
                    final_harvest_indicator,
                    t,
                    "Eucapyltus",
                    j,
                    i,
                    stand_id_str,
                )
                * model.x_eucalyptus[i, j]
                for j in model.J_euca
                if (i, j) in model.x_eucalyptus
            )

        return 0.0

    if mode == "hard_final_harvest":

        def no_adjacent_final_harvest_rule(model, s, r, t):
            return final_harvest_expr(model, s, t) + final_harvest_expr(model, r, t) <= 1

        model.no_adjacent_final_harvest_ext = Constraint(
            model.adjacency_edges_ext,
            model.T,
            rule=no_adjacent_final_harvest_rule,
        )

        model.adjacency_extension_mode = "hard_final_harvest"

    elif mode == "penalty_final_harvest":

        model.adjacent_final_harvest_ext = Var(
            model.adjacency_edges_ext,
            model.T,
            bounds=(0.0, 1.0),
        )

        def adjacent_final_harvest_lb_rule(model, s, r, t):
            return model.adjacent_final_harvest_ext[s, r, t] >= (
                final_harvest_expr(model, s, t)
                + final_harvest_expr(model, r, t)
                - 1.0
            )

        model.adjacent_final_harvest_lb_ext = Constraint(
            model.adjacency_edges_ext,
            model.T,
            rule=adjacent_final_harvest_lb_rule,
        )

        def adjacency_penalty_expression_rule(model):
            return sum(
                model.adjacency_weight_ext[s, r]
                * model.adjacent_final_harvest_ext[s, r, t]
                for (s, r) in model.adjacency_edges_ext
                for t in model.T
            )

        model.adjacency_penalty_value_ext = Expression(
            rule=adjacency_penalty_expression_rule
        )

        if adjacency_scale is None:
            adjacency_scale = sum(float(w) for w in edge_weights.values()) * len(list(model.T))
            adjacency_scale = max(float(adjacency_scale), 1.0)

        model.adjacency_scale_ext = Param(initialize=float(adjacency_scale))
        model.adjacency_phi_ext = Param(initialize=float(phi))

        old_objective = _active_objective(model)
        old_expr = old_objective.expr
        old_sense = old_objective.sense
        old_objective.deactivate()

        model.base_objective_before_adjacency_ext = Expression(expr=old_expr)

        if base_objective_is_normalized:
            scaled_base_expr = model.base_objective_before_adjacency_ext
        else:
            if base_objective_scale is None:
                raise ValueError(
                    "base_objective_scale is required when "
                    "base_objective_is_normalized=False. "
                    "Use a positive scale such as the base NPV value, "
                    "or set base_objective_is_normalized=True if the active "
                    "objective is already normalized."
                )

            base_objective_scale = max(abs(float(base_objective_scale)), 1.0)
            model.base_objective_scale_ext = Param(initialize=float(base_objective_scale))
            scaled_base_expr = (
                model.base_objective_before_adjacency_ext
                / model.base_objective_scale_ext
            )

        model.scaled_base_objective_ext = Expression(expr=scaled_base_expr)

        penalty_term = (
            model.adjacency_phi_ext
            * model.adjacency_penalty_value_ext
            / model.adjacency_scale_ext
        )

        if old_sense == maximize:
            new_expr = model.scaled_base_objective_ext - penalty_term
        else:
            new_expr = model.scaled_base_objective_ext + penalty_term

        model.objective_with_adjacency_ext = Objective(
            expr=new_expr,
            sense=old_sense,
        )

        model.adjacency_extension_mode = "penalty_final_harvest"

    return model

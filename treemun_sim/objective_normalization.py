"""
Objective-normalization utilities for treemun-sim Pyomo models.

This module lets you replace the active objective of an already-created model
with a normalized weighted objective, without editing optimization.py.

Recommended use for the spatial v1.4.0 tests:

    model = tm.forest_management_optimization_model(...)
    model = replace_with_normalized_weighted_objective(
        model,
        npv_weight=0.5,
        carbon_weight=0.5,
        npv_scale=NPV_IDEAL,
        carbon_scale=CARBON_IDEAL,
    )
    model = add_final_harvest_adjacency(
        model,
        ...,
        mode="penalty_final_harvest",
        phi=0.10,
        base_objective_is_normalized=True,
    )

The resulting objective is:

    npv_weight * NPV / npv_scale
    + carbon_weight * Carbon / carbon_scale

and the adjacency extension can then subtract:

    phi * AdjPenalty / adjacency_scale
"""

from pyomo.environ import Expression, Objective, Param, maximize, value


def _delete_component_if_exists(model, name):
    """Delete a Pyomo component if it already exists."""
    if hasattr(model, name):
        model.del_component(getattr(model, name))


def _active_objective(model):
    """Return the only active objective or raise a clear error."""
    active_objectives = list(model.component_objects(Objective, active=True))
    if len(active_objectives) != 1:
        raise ValueError(
            f"Expected exactly one active objective, found {len(active_objectives)}."
        )
    return active_objectives[0]


def _first_existing_attr(model, names, label):
    """Return the first existing model attribute from a list of candidate names."""
    for name in names:
        if hasattr(model, name):
            return getattr(model, name), name
    raise AttributeError(
        f"Could not find {label} expression. Tried attributes: {names}. "
        "Pass the expression explicitly using npv_expr=... or carbon_expr=...."
    )


def objective_value(model):
    """Return the value of the active objective."""
    obj = _active_objective(model)
    return value(obj.expr)


def component_values(model):
    """
    Return available objective-component values from a solved model.
    """
    out = {}
    for name in [
        "npv_value",
        "carbon_seq_value",
        "normalized_npv_value_ext",
        "normalized_carbon_seq_value_ext",
        "normalized_weighted_objective_value_ext",
        "adjacency_penalty_value_ext",
        "scaled_base_objective_ext",
    ]:
        if hasattr(model, name):
            try:
                out[name] = value(getattr(model, name))
            except Exception:
                out[name] = None
    return out


def replace_with_normalized_weighted_objective(
    model,
    npv_weight=0.5,
    carbon_weight=0.5,
    npv_scale=None,
    carbon_scale=None,
    npv_expr=None,
    carbon_expr=None,
    deactivate_existing=True,
    objective_name="normalized_weighted_objective_ext",
):
    """
    Replace the active objective with a normalized NPV-carbon weighted objective.

    Parameters
    ----------
    model : pyomo.environ.ConcreteModel
        Existing treemun-sim Pyomo model.
    npv_weight : float
        Weight assigned to normalized NPV.
    carbon_weight : float
        Weight assigned to normalized carbon.
    npv_scale : float
        Positive scale for NPV, ideally the NPV-only optimum or another ideal
        reference value. If None, model.npv_scale is used if available.
    carbon_scale : float
        Positive scale for carbon, ideally the carbon-only optimum or another
        ideal reference value. If None, model.carbon_scale is used if available.
    npv_expr : Pyomo expression or None
        Optional explicit NPV expression. If None, the function searches common
        model attributes such as model.npv_value.
    carbon_expr : Pyomo expression or None
        Optional explicit carbon expression. If None, the function searches common
        model attributes such as model.carbon_seq_value.
    deactivate_existing : bool
        If True, deactivate the current active objective.
    objective_name : str
        Name of the new Pyomo Objective component.

    Returns
    -------
    model : pyomo.environ.ConcreteModel
        Same model, modified in-place.
    """
    npv_weight = float(npv_weight)
    carbon_weight = float(carbon_weight)

    if npv_weight < 0.0 or carbon_weight < 0.0:
        raise ValueError("npv_weight and carbon_weight must be non-negative.")

    total_weight = npv_weight + carbon_weight
    if total_weight <= 0.0:
        raise ValueError("At least one of npv_weight or carbon_weight must be positive.")

    # Normalize the weights so users can pass 50/50 or 0.5/0.5.
    npv_weight = npv_weight / total_weight
    carbon_weight = carbon_weight / total_weight

    if npv_expr is None:
        npv_expr, npv_attr = _first_existing_attr(
            model,
            ["npv_value", "NPV_value", "npv_expr", "NPV_expr"],
            "NPV",
        )
    else:
        npv_attr = "<explicit>"

    if carbon_expr is None:
        carbon_expr, carbon_attr = _first_existing_attr(
            model,
            ["carbon_seq_value", "carbon_value", "carbon_expr", "CarbSeqOPT"],
            "carbon",
        )
    else:
        carbon_attr = "<explicit>"

    if npv_scale is None:
        if hasattr(model, "npv_scale"):
            npv_scale = value(model.npv_scale)
        else:
            raise ValueError(
                "npv_scale is required because the model has no model.npv_scale attribute."
            )

    if carbon_scale is None:
        if hasattr(model, "carbon_scale"):
            carbon_scale = value(model.carbon_scale)
        else:
            raise ValueError(
                "carbon_scale is required because the model has no model.carbon_scale attribute."
            )

    npv_scale = max(abs(float(npv_scale)), 1.0)
    carbon_scale = max(abs(float(carbon_scale)), 1.0)

    # Delete old extension components if rerunning.
    for name in [
        "normalized_npv_scale_ext",
        "normalized_carbon_scale_ext",
        "normalized_npv_weight_ext",
        "normalized_carbon_weight_ext",
        "normalized_npv_value_ext",
        "normalized_carbon_seq_value_ext",
        "normalized_weighted_objective_value_ext",
        objective_name,
    ]:
        _delete_component_if_exists(model, name)

    model.normalized_npv_scale_ext = Param(initialize=float(npv_scale))
    model.normalized_carbon_scale_ext = Param(initialize=float(carbon_scale))
    model.normalized_npv_weight_ext = Param(initialize=float(npv_weight))
    model.normalized_carbon_weight_ext = Param(initialize=float(carbon_weight))

    model.normalized_npv_value_ext = Expression(
        expr=npv_expr / model.normalized_npv_scale_ext
    )
    model.normalized_carbon_seq_value_ext = Expression(
        expr=carbon_expr / model.normalized_carbon_scale_ext
    )

    model.normalized_weighted_objective_value_ext = Expression(
        expr=(
            model.normalized_npv_weight_ext * model.normalized_npv_value_ext
            + model.normalized_carbon_weight_ext * model.normalized_carbon_seq_value_ext
        )
    )

    if deactivate_existing:
        old_objective = _active_objective(model)
        old_objective.deactivate()

    setattr(
        model,
        objective_name,
        Objective(expr=model.normalized_weighted_objective_value_ext, sense=maximize),
    )

    model.objective_mode = "normalized_weighted_npv_carbon_ext"
    model.normalization_metadata_ext = {
        "npv_expression": npv_attr,
        "carbon_expression": carbon_attr,
        "npv_scale": npv_scale,
        "carbon_scale": carbon_scale,
        "npv_weight": npv_weight,
        "carbon_weight": carbon_weight,
    }

    return model

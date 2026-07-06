# treemun/treemun_sim/optimization.py
"""
Optimization module for treemun forest management models.
Provides functions to create, solve, and extract results from a forest optimization model example.
"""

from pyomo.environ import *
from pyomo.opt import SolverFactory
import os


VALID_OBJECTIVES = {"npv", "carbon", "weighted"}

OBJECTIVE_ALIASES = {
    "npv": "npv",
    "NPV": "npv",
    "carbon": "carbon",
    "carbseq": "carbon",
    "carb_seq": "carbon",
    "carbon_seq": "carbon",
    "carbonsequestration": "carbon",
    "carbon_sequestration": "carbon",
    "weighted": "weighted",
    "biobjective": "weighted",
    "bi-objective": "weighted",
    "biobjetivo": "weighted",
    "weighted_biobjective": "weighted",
}


def _as_period_array(value, horizon, name):
    """Convert a scalar or period list into a list of length horizon."""
    if isinstance(value, (int, float)):
        return [value] * horizon

    value_array = list(value)
    if len(value_array) != horizon:
        raise ValueError(f"{name} must have length {horizon}, got {len(value_array)}")

    return value_array


def _normalize_objective(objective):
    """Return canonical objective name: npv, carbon, or weighted."""
    if objective is None:
        objective = "npv"

    if not isinstance(objective, str):
        raise TypeError("objective must be a string: 'npv', 'carbon', or 'weighted'.")

    key = objective.strip()
    key_lower = key.lower()

    if key in OBJECTIVE_ALIASES:
        return OBJECTIVE_ALIASES[key]

    if key_lower in OBJECTIVE_ALIASES:
        return OBJECTIVE_ALIASES[key_lower]

    raise ValueError(
        "objective must be one of 'npv', 'carbon', or 'weighted'. "
        f"Got {objective!r}."
    )


def _validate_even_flow_tolerance(even_flow_tolerance):
    """Validate even-flow tolerance as a fraction in [0, 1]."""
    if even_flow_tolerance is None:
        return 0.0

    even_flow_tolerance = float(even_flow_tolerance)

    if even_flow_tolerance < 0.0 or even_flow_tolerance > 1.0:
        raise ValueError(
            "even_flow_tolerance must be between 0 and 1. "
            "For example, use 0.05 for a 5% allowed decrease."
        )

    return even_flow_tolerance


def _validate_objective_configuration(
    objective,
    carbon_i_j_t,
    npv_weight,
    carbon_weight,
):
    """Validate objective-mode arguments."""
    objective = _normalize_objective(objective)

    if objective in {"carbon", "weighted"} and carbon_i_j_t is None:
        raise ValueError(
            "carbon_i_j_t is required when objective='carbon' or objective='weighted'. "
            "Pass the carbon_estimada dictionary generated with Carbon=True and "
            "return_carbon_opti=True."
        )

    if objective == "weighted":
        npv_weight = float(npv_weight)
        carbon_weight = float(carbon_weight)

        if npv_weight < 0.0 or carbon_weight < 0.0:
            raise ValueError("npv_weight and carbon_weight must be non-negative.")

        if npv_weight + carbon_weight <= 0.0:
            raise ValueError("At least one of npv_weight or carbon_weight must be positive.")

    return objective


def forest_management_optimization_model(
    bosque,
    a_i_j_T,
    a_i_j_t,
    horizon,
    pine_revenue=9,
    eucalyptus_revenue=10,
    min_ending_biomass=30000,
    discount_rate=0.08,
    even_flow_tolerance=0.0,
    objective="npv",
    carbon_i_j_t=None,
    npv_weight=0.5,
    carbon_weight=0.5,
    npv_scale=None,
    carbon_scale=None,
):
    """
    Creates and returns a forest management optimization model using Pyomo.

    objective options:
        objective="npv"      -> original NPV maximization.
        objective="carbon"   -> maximize CarbSeqOPT / carbon_i_j_t.
        objective="weighted" -> normalized weighted sum of NPV and CarbSeqOPT.

    even_flow_tolerance:
        0.0  -> original constraint H[t+1] >= H[t].
        0.05 -> allows H[t+1] >= 0.95 H[t].
        0.10 -> allows H[t+1] >= 0.90 H[t].
    """

    even_flow_tolerance = _validate_even_flow_tolerance(even_flow_tolerance)

    objective = _validate_objective_configuration(
        objective=objective,
        carbon_i_j_t=carbon_i_j_t,
        npv_weight=npv_weight,
        carbon_weight=carbon_weight,
    )

    pine_revenue_array = _as_period_array(pine_revenue, horizon, "pine_revenue")
    eucalyptus_revenue_array = _as_period_array(
        eucalyptus_revenue,
        horizon,
        "eucalyptus_revenue",
    )

    I_pino = set()
    I_euca = set()
    J_pino = set()
    J_euca = set()

    for df in bosque:
        pinus_df = df[df["Especie"] == "Pinus"]
        I_pino.update(pinus_df["id_rodal"].unique())

        # treemun currently uses the string "Eucapyltus" in its outputs.
        euca_df = df[df["Especie"] == "Eucapyltus"]
        I_euca.update(euca_df["id_rodal"].unique())

        for policy in df["politica"].unique():
            if "pino" in policy:
                J_pino.add(policy)
            elif "eucalyptus" in policy:
                J_euca.add(policy)

    model = ConcreteModel()

    model.objective_mode = objective

    model.I_pino = Set(initialize=sorted(I_pino))
    model.I_euca = Set(initialize=sorted(I_euca))
    model.J_pino = Set(initialize=sorted(J_pino))
    model.J_euca = Set(initialize=sorted(J_euca))
    model.T = RangeSet(1, horizon)
    model.Epino = Set(initialize=["Pinus"])
    model.Eeuca = Set(initialize=["Eucapyltus"])

    model.pine_revenue = Param(
        model.T,
        initialize={t: pine_revenue_array[t - 1] for t in model.T},
    )
    model.eucalyptus_revenue = Param(
        model.T,
        initialize={t: eucalyptus_revenue_array[t - 1] for t in model.T},
    )

    model.min_ending_biomass = Param(initialize=min_ending_biomass)
    model.discount_rate = Param(initialize=discount_rate)
    model.even_flow_tolerance = Param(initialize=even_flow_tolerance)

    valid_pino_indices = [
        (i, j)
        for i in model.I_pino
        for j in model.J_pino
        if any((t, e, j, i) in a_i_j_t for t in model.T for e in model.Epino)
    ]

    valid_euca_indices = [
        (i, j)
        for i in model.I_euca
        for j in model.J_euca
        if any((t, e, j, i) in a_i_j_t for t in model.T for e in model.Eeuca)
    ]

    model.valid_pino_indices = Set(dimen=2, initialize=valid_pino_indices)
    model.valid_euca_indices = Set(dimen=2, initialize=valid_euca_indices)

    model.x_pine = Var(valid_pino_indices, within=Binary)
    model.x_eucalyptus = Var(valid_euca_indices, within=Binary)
    model.harvest_volume = Var(model.T, within=NonNegativeReals)

    def npv_expression_rule(model):
        pine_npv = sum(
            a_i_j_t[(t, e, j, i)]
            * model.x_pine[i, j]
            * model.pine_revenue[t]
            / (1 + model.discount_rate) ** t
            for t in model.T
            for e in model.Epino
            for j in model.J_pino
            for i in model.I_pino
            if (i, j) in valid_pino_indices and (t, e, j, i) in a_i_j_t
        )

        eucalyptus_npv = sum(
            a_i_j_t[(t, e, j, i)]
            * model.x_eucalyptus[i, j]
            * model.eucalyptus_revenue[t]
            / (1 + model.discount_rate) ** t
            for t in model.T
            for e in model.Eeuca
            for j in model.J_euca
            for i in model.I_euca
            if (i, j) in valid_euca_indices and (t, e, j, i) in a_i_j_t
        )

        return pine_npv + eucalyptus_npv

    model.npv_value = Expression(rule=npv_expression_rule)

    def carbon_expression_rule(model):
        if carbon_i_j_t is None:
            return 0.0

        pine_carbon = sum(
            carbon_i_j_t[(t, e, j, i)] * model.x_pine[i, j]
            for t in model.T
            for e in model.Epino
            for j in model.J_pino
            for i in model.I_pino
            if (i, j) in valid_pino_indices and (t, e, j, i) in carbon_i_j_t
        )

        eucalyptus_carbon = sum(
            carbon_i_j_t[(t, e, j, i)] * model.x_eucalyptus[i, j]
            for t in model.T
            for e in model.Eeuca
            for j in model.J_euca
            for i in model.I_euca
            if (i, j) in valid_euca_indices and (t, e, j, i) in carbon_i_j_t
        )

        return pine_carbon + eucalyptus_carbon

    model.carbon_seq_value = Expression(rule=carbon_expression_rule)

    if npv_scale is None:
        npv_scale = sum(
            abs(
                a_i_j_t[(t, e, j, i)]
                * pine_revenue_array[t - 1]
                / (1 + discount_rate) ** t
            )
            for t in range(1, horizon + 1)
            for e in ["Pinus"]
            for j in J_pino
            for i in I_pino
            if (i, j) in valid_pino_indices and (t, e, j, i) in a_i_j_t
        ) + sum(
            abs(
                a_i_j_t[(t, e, j, i)]
                * eucalyptus_revenue_array[t - 1]
                / (1 + discount_rate) ** t
            )
            for t in range(1, horizon + 1)
            for e in ["Eucapyltus"]
            for j in J_euca
            for i in I_euca
            if (i, j) in valid_euca_indices and (t, e, j, i) in a_i_j_t
        )

        npv_scale = max(float(npv_scale), 1.0)

    if carbon_scale is None:
        if carbon_i_j_t is None:
            carbon_scale = 1.0
        else:
            carbon_scale = sum(
                abs(carbon_i_j_t[(t, e, j, i)])
                for t in range(1, horizon + 1)
                for e in ["Pinus"]
                for j in J_pino
                for i in I_pino
                if (i, j) in valid_pino_indices and (t, e, j, i) in carbon_i_j_t
            ) + sum(
                abs(carbon_i_j_t[(t, e, j, i)])
                for t in range(1, horizon + 1)
                for e in ["Eucapyltus"]
                for j in J_euca
                for i in I_euca
                if (i, j) in valid_euca_indices and (t, e, j, i) in carbon_i_j_t
            )

            carbon_scale = max(float(carbon_scale), 1.0)

    model.npv_scale = Param(initialize=float(npv_scale))
    model.carbon_scale = Param(initialize=float(carbon_scale))
    model.npv_weight = Param(initialize=float(npv_weight))
    model.carbon_weight = Param(initialize=float(carbon_weight))

    if objective == "npv":
        model.objective = Objective(expr=model.npv_value, sense=maximize)

    elif objective == "carbon":
        model.objective = Objective(expr=model.carbon_seq_value, sense=maximize)

    elif objective == "weighted":
        model.objective = Objective(
            expr=(
                model.npv_weight * model.npv_value / model.npv_scale
                + model.carbon_weight * model.carbon_seq_value / model.carbon_scale
            ),
            sense=maximize,
        )

    else:
        raise RuntimeError("Invalid objective configuration.")

    def single_assignment_pine_rule(model, i):
        return sum(
            model.x_pine[i, j]
            for j in model.J_pino
            if (i, j) in valid_pino_indices
        ) == 1

    def single_assignment_eucalyptus_rule(model, i):
        return sum(
            model.x_eucalyptus[i, j]
            for j in model.J_euca
            if (i, j) in valid_euca_indices
        ) == 1

    model.single_assignment_pine = Constraint(
        model.I_pino,
        rule=single_assignment_pine_rule,
    )
    model.single_assignment_eucalyptus = Constraint(
        model.I_euca,
        rule=single_assignment_eucalyptus_rule,
    )

    def harvest_volume_tracking_rule(model, t):
        return sum(
            a_i_j_t[(t, e, j, i)] * model.x_pine[i, j]
            for e in model.Epino
            for j in model.J_pino
            for i in model.I_pino
            if (t, e, j, i) in a_i_j_t
        ) + sum(
            a_i_j_t[(t, e, j, i)] * model.x_eucalyptus[i, j]
            for e in model.Eeuca
            for j in model.J_euca
            for i in model.I_euca
            if (t, e, j, i) in a_i_j_t
        ) == model.harvest_volume[t]

    model.harvest_volume_tracking = Constraint(
        model.T,
        rule=harvest_volume_tracking_rule,
    )

    def even_flow_rule(model, t):
        if t < model.T.last():
            return model.harvest_volume[t + 1] >= (
                1.0 - model.even_flow_tolerance
            ) * model.harvest_volume[t]
        return Constraint.Skip

    model.even_flow = Constraint(model.T, rule=even_flow_rule)

    def sustainability_rule(model):
        total_ending_biomass = sum(
            a_i_j_T.get((i, j), 0) * model.x_pine[i, j]
            for (i, j) in valid_pino_indices
            if (i, j) in a_i_j_T
        ) + sum(
            a_i_j_T.get((i, j), 0) * model.x_eucalyptus[i, j]
            for (i, j) in valid_euca_indices
            if (i, j) in a_i_j_T
        )

        return total_ending_biomass >= model.min_ending_biomass

    model.sustainability = Constraint(rule=sustainability_rule)

    return model

def solve_model(model, solver_name, gap=0.01, executable_path=None, tee=True):
    """
    Solves a Pyomo model, requiring the solver to be in the system's PATH
    or for its path to be specified explicitly.
    
    Args:
        model (Pyomo Model): The optimization model to be solved.
        solver_name (str): Name of the solver ('cplex' or 'cbc').
        gap (float, optional): The relative optimality gap. Defaults to 0.01.
        executable_path (str, optional): Direct path to the solver's executable.
                                          If None, the solver is assumed to be in the system's PATH.
                                          Defaults to None.
        tee (bool, optional): If True, displays the solver's output in the console. Defaults to True.
        
    Returns:
        results: The Pyomo results object from the solver.
    """
    solver_name = solver_name.lower()
    
    # If a path is provided, verify that it exists.
    if executable_path and not os.path.exists(executable_path):
        raise FileNotFoundError(f"The specified executable was not found at: {executable_path}")
    
    # The final path is the one provided by the user, or None.
    # If it's None, Pyomo will search for the solver in the system's PATH.
    solver = SolverFactory(solver_name, executable=executable_path)
    
    # Configure solver-specific options
    if solver_name == 'cplex':
        solver.options['mipgap'] = gap
    elif solver_name == 'cbc':
        solver.options['ratioGap'] = gap  # Note: The option is named 'ratioGap' in CBC
    else:
        raise ValueError(f"Solver '{solver_name}' is not supported or the name is incorrect. Choose from 'cplex' or 'cbc'")
    
    # Solve the Model
    log_filename = f"log_{solver_name}.txt"
    print(f"--- Solving with {solver_name.upper()} | Gap: {gap*100}% ---")
    results = solver.solve(model, tee=tee, logfile=log_filename)
    print(f"--- Solving finished. Log saved to '{log_filename}' ---")
    
    return results


def extract_results(model, results):
    """
    Extracts key results from a solved Pyomo model.

    Returns a dictionary with:
        - objective_value
        - objective_mode
        - npv_value
        - carbon_seq_value
        - total_harvest_per_period
        - selected pine and eucalyptus stand-policy assignments
    """
    term_cond = results.solver.termination_condition

    if term_cond == TerminationCondition.optimal or term_cond == TerminationCondition.feasible:

        objective_value = value(model.objective)
        harvest_vector = [model.harvest_volume[t].value for t in model.T]

        xpino_values = [
            (i, j)
            for (i, j) in model.x_pine
            if model.x_pine[i, j].value is not None
            and model.x_pine[i, j].value > 1e-6
        ]

        xeuca_values = [
            (i, j)
            for (i, j) in model.x_eucalyptus
            if model.x_eucalyptus[i, j].value is not None
            and model.x_eucalyptus[i, j].value > 1e-6
        ]

        output_data = {
            "objective_value": objective_value,
            "objective_mode": getattr(model, "objective_mode", "unknown"),
            "npv_value": value(model.npv_value) if hasattr(model, "npv_value") else None,
            "carbon_seq_value": (
                value(model.carbon_seq_value)
                if hasattr(model, "carbon_seq_value")
                else None
            ),
            "npv_scale": value(model.npv_scale) if hasattr(model, "npv_scale") else None,
            "carbon_scale": (
                value(model.carbon_scale)
                if hasattr(model, "carbon_scale")
                else None
            ),
            "npv_weight": value(model.npv_weight) if hasattr(model, "npv_weight") else None,
            "carbon_weight": (
                value(model.carbon_weight)
                if hasattr(model, "carbon_weight")
                else None
            ),
            "even_flow_tolerance": (
                value(model.even_flow_tolerance)
                if hasattr(model, "even_flow_tolerance")
                else None
            ),
            "total_harvest_per_period": harvest_vector,
            "pinus_stand_plan": xpino_values,
            "total_pinus_stand_treated": len(xpino_values),
            "eucalyptus_stand_plan": xeuca_values,
            "total_eucalyptus_stand_treated": len(xeuca_values),
        }

        return output_data

    print(f"\nAn optimal solution was not found. Termination condition: {term_cond}")
    return None


# ---------------------------------------------------------------------
# Decision-support front utilities added in v1.3.0
# ---------------------------------------------------------------------

def _is_nondominated_2d(df, x_col="npv_value", y_col="carbon_seq_value", tol=1e-9):
    import numpy as np

    values = df[[x_col, y_col]].to_numpy(dtype=float)
    n = len(values)
    nondominated = np.ones(n, dtype=bool)

    for i in range(n):
        xi, yi = values[i]

        for j in range(n):
            if i == j:
                continue

            xj, yj = values[j]

            dominates = (
                xj >= xi - tol
                and yj >= yi - tol
                and (xj > xi + tol or yj > yi + tol)
            )

            if dominates:
                nondominated[i] = False
                break

    return nondominated


def _identify_knee_by_ideal_distance(df, x_col="npv_value", y_col="carbon_seq_value"):
    import numpy as np

    if df.empty:
        return None

    x = df[x_col].astype(float).to_numpy()
    y = df[y_col].astype(float).to_numpy()

    x_min, x_max = np.min(x), np.max(x)
    y_min, y_max = np.min(y), np.max(y)

    x_norm = np.ones_like(x) if abs(x_max - x_min) < 1e-12 else (x - x_min) / (x_max - x_min)
    y_norm = np.ones_like(y) if abs(y_max - y_min) < 1e-12 else (y - y_min) / (y_max - y_min)

    distance_to_ideal = np.sqrt((1.0 - x_norm) ** 2 + (1.0 - y_norm) ** 2)
    local_pos = int(np.argmin(distance_to_ideal))

    return df.index[local_pos]


def _solve_model_compat(model, solver_name="cbc", executable_path=None, gap=0.01, tee=False):
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
            return solve_model(
                model,
                solver_name=solver_name,
            )




def _safe_to_csv(df, path, index=False):
    """
    Safely exports a DataFrame to CSV by replacing NaN/None values with
    empty cells. This avoids pandas RuntimeWarning messages when casting
    missing values to strings during CSV export.
    """
    import pandas as pd
    import warnings

    if df is None:
        df = pd.DataFrame()

    df_out = df.copy()

    # Keep numeric columns numeric where possible, but avoid NaN casting warnings.
    df_out = df_out.where(pd.notnull(df_out), "")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        df_out.to_csv(path, index=index)

def _sanitize_filename(value):
    import re

    value = str(value).strip().replace(" ", "_")
    value = re.sub(r"[^A-Za-z0-9_\-\.]+", "_", value)
    value = re.sub(r"_+", "_", value)

    return value.strip("_")


def _looks_like_policy(value):
    value = str(value).lower()
    return "policy" in value or "polit" in value or "prescription" in value


def _looks_like_stand(value):
    value = str(value).lower()
    return "stand" in value or "rodal" in value


def _infer_stand_policy_from_index(index_value):
    if isinstance(index_value, tuple):
        idx = index_value
    else:
        idx = (index_value,)

    if len(idx) == 1:
        return idx[0], None

    a, b = idx[0], idx[1]

    if _looks_like_policy(a) and not _looks_like_policy(b):
        return b, a

    if _looks_like_policy(b) and not _looks_like_policy(a):
        return a, b

    if _looks_like_stand(b) and not _looks_like_stand(a):
        return b, a

    return a, b




def _policy_number(value):
    """
    Extracts the final numeric identifier from a policy label.

    Examples:
        'policy_pino 1' -> '1'
        'policy_eucalyptus 3' -> '3'
        2 -> '2'
    """
    import re

    if value is None:
        return None

    s = str(value)
    nums = re.findall(r"\d+", s)

    if not nums:
        return None

    return nums[-1]


def _species_from_text(value):
    if value is None:
        return None

    low = str(value).lower()

    if "pino" in low or "pinus" in low or "pira" in low:
        return "Pinus"

    if "euca" in low or "eucalyptus" in low or "eucalypt" in low:
        return "Eucalyptus"

    return None


def _species_from_var_name(var_name):
    return _species_from_text(var_name)


def _standardize_summary_metadata(resumen=None):
    """
    Converts resumen_c into a standard metadata DataFrame.

    Expected resumen_c structure:
        [
            {
                'id_rodal': 'stand1',
                'especie': 'Pinus',
                'has': 5.31,
                'edad_inicial': 3,
                'edad_final': 12,
                'policy': 'policy_pino 1',
                'ecuacion_inicial_id': 25,
            },
            ...
        ]
    """
    import pandas as pd

    if resumen is None:
        return pd.DataFrame()

    if isinstance(resumen, pd.DataFrame):
        df = resumen.copy()
    else:
        df = pd.DataFrame(list(resumen))

    if df.empty:
        return pd.DataFrame()

    rename_map = {
        "id_rodal": "stand",
        "rodal": "stand",
        "stand_id": "stand",
        "stand": "stand",
        "especie": "species",
        "species": "species",
        "has": "area_ha",
        "ha": "area_ha",
        "area": "area_ha",
        "edad_inicial": "initial_age",
        "edad_final": "final_age",
        "policy": "policy",
        "politica": "policy",
        "política": "policy",
        "ecuacion_inicial_id": "equation_id",
        "equation_id": "equation_id",
        "equation_initial_id": "equation_id",
    }

    normalized = {}

    for col in df.columns:
        key = str(col).strip().lower()
        normalized[col] = rename_map.get(key, col)

    df = df.rename(columns=normalized)

    required = ["stand", "policy"]

    for col in required:
        if col not in df.columns:
            return pd.DataFrame()

    if "species" not in df.columns:
        df["species"] = df["policy"].apply(_species_from_text)

    if "area_ha" not in df.columns:
        df["area_ha"] = None

    if "initial_age" not in df.columns:
        df["initial_age"] = None

    if "final_age" not in df.columns:
        df["final_age"] = None

    if "equation_id" not in df.columns:
        df["equation_id"] = None

    df["stand"] = df["stand"].astype(str)
    df["policy"] = df["policy"].astype(str)
    df["species"] = df["species"].astype(str)
    df["policy_number"] = df["policy"].apply(_policy_number)

    keep_cols = [
        "stand",
        "species",
        "policy",
        "policy_number",
        "area_ha",
        "initial_age",
        "final_age",
        "equation_id",
    ]

    df = df[keep_cols].drop_duplicates()

    return df


def _normalize_colname(name):
    return (
        str(name)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace(".", "_")
    )


def _find_column(df, candidates):
    normalized = {_normalize_colname(c): c for c in df.columns}

    for cand in candidates:
        key = _normalize_colname(cand)

        if key in normalized:
            return normalized[key]

    return None


def _standardize_equation_metadata(df):
    """
    Standardizes a table that maps equation_id to site_index and zone.
    """
    import pandas as pd

    if df is None:
        return pd.DataFrame()

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)

    if df.empty:
        return pd.DataFrame()

    equation_col = _find_column(
        df,
        [
            "equation_id",
            "ecuacion_inicial_id",
            "ecuacion_id",
            "id_ecuacion",
            "equation_initial_id",
            "id",
        ],
    )

    site_col = _find_column(
        df,
        [
            "site_index",
            "siteindex",
            "site index",
            "indice_sitio",
            "índice_sitio",
            "is",
            "si",
            "site",
        ],
    )

    zone_col = _find_column(
        df,
        [
            "zone",
            "zona",
            "z",
            "geographical_zone",
            "geographic_zone",
            "growth_zone",
            "zona_geografica",
            "zona_geográfica",
        ],
    )

    if equation_col is None:
        return pd.DataFrame()

    out = pd.DataFrame()
    out["equation_id"] = df[equation_col]

    if site_col is not None:
        out["site_index"] = df[site_col]
    else:
        out["site_index"] = None

    if zone_col is not None:
        out["zone"] = df[zone_col]
    else:
        out["zone"] = None

    out = out.drop_duplicates(subset=["equation_id"])

    return out


def _equation_metadata_from_bosque(bosque):
    """
    Tries to find equation_id -> site_index/zone metadata inside bosque.
    """
    import pandas as pd

    frames = []

    if bosque is None:
        return pd.DataFrame()

    for obj in bosque:
        if isinstance(obj, pd.DataFrame) and not obj.empty:
            meta = _standardize_equation_metadata(obj)

            if not meta.empty:
                frames.append(meta)

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset=["equation_id"])

    return out


def _equation_metadata_from_package_data():
    """
    Tries to find equation_id -> site_index/zone metadata in treemun_sim/data CSVs.
    This is defensive and only works if the CSVs contain recognizable columns.
    """
    import pandas as pd
    from pathlib import Path

    frames = []

    data_dir = Path(__file__).resolve().parent / "data"

    if not data_dir.exists():
        return pd.DataFrame()

    for csv_path in data_dir.glob("*.csv"):
        try:
            df = pd.read_csv(csv_path)
            meta = _standardize_equation_metadata(df)

            if not meta.empty:
                frames.append(meta)

        except Exception:
            continue

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset=["equation_id"])

    return out


def _build_policy_metadata(resumen=None, bosque=None, equation_metadata=None):
    """
    Builds policy metadata using resumen_c as the primary source of truth.
    """
    import pandas as pd

    meta = _standardize_summary_metadata(resumen)

    if meta.empty:
        return pd.DataFrame()

    eq_meta = pd.DataFrame()

    if equation_metadata is not None:
        eq_meta = _standardize_equation_metadata(equation_metadata)

    if eq_meta.empty:
        eq_meta = _equation_metadata_from_bosque(bosque)

    if eq_meta.empty:
        eq_meta = _equation_metadata_from_package_data()

    if not eq_meta.empty and "equation_id" in meta.columns:
        meta = meta.merge(eq_meta, on="equation_id", how="left")
    else:
        meta["site_index"] = None
        meta["zone"] = None

    return meta


def _infer_stand_policy_from_index(index_value):
    """
    Infer stand and policy from a Pyomo variable index.
    """
    if isinstance(index_value, tuple):
        idx = index_value
    else:
        idx = (index_value,)

    if len(idx) == 1:
        return idx[0], None

    a, b = idx[0], idx[1]

    a_text = str(a).lower()
    b_text = str(b).lower()

    a_is_policy = "policy" in a_text or "polit" in a_text or "prescription" in a_text
    b_is_policy = "policy" in b_text or "polit" in b_text or "prescription" in b_text

    a_is_stand = "stand" in a_text or "rodal" in a_text
    b_is_stand = "stand" in b_text or "rodal" in b_text

    if a_is_policy and not b_is_policy:
        return b, a

    if b_is_policy and not a_is_policy:
        return a, b

    if b_is_stand and not a_is_stand:
        return b, a

    return a, b


def _raw_selected_xij_from_model(model, tol=1e-6):
    """
    Extracts only selected x_ij-like variables from the model.
    This function does not assign final species; species is corrected later
    using resumen_c.
    """
    import pandas as pd
    from pyomo.environ import Var, value

    records = []

    for var in model.component_objects(Var, active=True):
        var_name = getattr(var, "name", "")
        low = str(var_name).lower()

        # Exclude known continuous/helper variables.
        if any(token in low for token in ["harvest", "volume", "carbon", "npv", "epsilon"]):
            continue

        # Keep assignment-like variables.
        looks_like_x = (
            low.startswith("x")
            or "_x" in low
            or "assign" in low
            or "policy" in low
            or "plan" in low
        )

        if not looks_like_x:
            continue

        species_guess = _species_from_var_name(var_name)

        try:
            indices = list(var)
        except TypeError:
            indices = [None]

        for idx in indices:
            try:
                if idx is None:
                    component = var
                    stand, policy = None, None
                else:
                    component = var[idx]
                    stand, policy = _infer_stand_policy_from_index(idx)

                x_value = value(component, exception=False)

                if x_value is None:
                    continue

                x_value = float(x_value)

                if x_value < 1.0 - tol:
                    continue

                policy_guess_species = _species_from_text(policy)
                species = species_guess or policy_guess_species

                records.append(
                    {
                        "stand": str(stand) if stand is not None else None,
                        "policy_raw": str(policy) if policy is not None else None,
                        "policy_number": _policy_number(policy),
                        "species_guess": species,
                        "x_value": x_value,
                        "source_variable": var_name,
                    }
                )

            except Exception:
                continue

    return pd.DataFrame(records)


def _selected_xij_from_output(output, tol=1e-6):
    """
    Fallback extraction from extract_results output.
    """
    import pandas as pd

    records = []

    if output is None:
        return pd.DataFrame()

    def add_record(stand, policy, x_value, species, source):
        try:
            x_value = float(x_value)
        except Exception:
            x_value = 1.0

        if x_value < 1.0 - tol:
            return

        records.append(
            {
                "stand": str(stand) if stand is not None else None,
                "policy_raw": str(policy) if policy is not None else None,
                "policy_number": _policy_number(policy),
                "species_guess": species,
                "x_value": x_value,
                "source_variable": source,
            }
        )

    def parse_plan(plan, species, source):
        if plan is None:
            return

        if isinstance(plan, dict):
            for k, v in plan.items():
                if isinstance(v, dict):
                    for kk, vv in v.items():
                        add_record(k, kk, vv, species, source)
                elif isinstance(k, tuple):
                    stand, policy = _infer_stand_policy_from_index(k)
                    add_record(stand, policy, v, species, source)
                elif isinstance(v, str):
                    add_record(k, v, 1.0, species, source)
                else:
                    add_record(k, None, v, species, source)

        elif isinstance(plan, (list, tuple)):
            for item in plan:
                if isinstance(item, dict):
                    stand = item.get("stand", item.get("rodal", item.get("id_rodal", None)))
                    policy = item.get("policy", item.get("politica", item.get("política", None)))
                    x_value = item.get("x_value", item.get("x", item.get("value", 1.0)))
                    add_record(stand, policy, x_value, species, source)

                elif isinstance(item, tuple):
                    if len(item) >= 3:
                        stand, policy = _infer_stand_policy_from_index(item[:2])
                        add_record(stand, policy, item[2], species, source)
                    elif len(item) >= 2:
                        stand, policy = _infer_stand_policy_from_index(item[:2])
                        add_record(stand, policy, 1.0, species, source)

    parse_plan(output.get("pinus_stand_plan", None), "Pinus", "extract_results_pinus")
    parse_plan(output.get("pino_stand_plan", None), "Pinus", "extract_results_pinus")
    parse_plan(output.get("eucalyptus_stand_plan", None), "Eucalyptus", "extract_results_eucalyptus")
    parse_plan(output.get("euca_stand_plan", None), "Eucalyptus", "extract_results_eucalyptus")

    return pd.DataFrame(records)


def _join_selected_xij_with_resumen(raw_xij, policy_meta):
    """
    Joins selected raw x_ij values with resumen_c metadata.

    Matching priority:
        1. stand + exact policy
        2. stand + policy_number + species_guess
        3. stand + policy_number, only if there is no ambiguity
    """
    import pandas as pd

    if raw_xij is None or raw_xij.empty:
        return pd.DataFrame()

    if policy_meta is None or policy_meta.empty:
        out = raw_xij.copy()
        out["species"] = out.get("species_guess", None)
        out["policy"] = out.get("policy_raw", None)
        return out

    raw = raw_xij.copy()
    meta = policy_meta.copy()

    raw["stand"] = raw["stand"].astype(str)
    meta["stand"] = meta["stand"].astype(str)
    meta["policy"] = meta["policy"].astype(str)

    rows = []

    # 1. Exact stand + policy
    exact = raw.merge(
        meta,
        left_on=["stand", "policy_raw"],
        right_on=["stand", "policy"],
        how="inner",
    )

    if not exact.empty:
        rows.append(exact)

    matched_idx = set(exact.index.tolist()) if not exact.empty else set()

    # 2. stand + policy_number + species_guess
    remaining = raw.copy()

    if not remaining.empty and "species_guess" in remaining.columns:
        with_species = remaining[remaining["species_guess"].notna()].copy()

        if not with_species.empty:
            by_num_species = with_species.merge(
                meta,
                left_on=["stand", "policy_number", "species_guess"],
                right_on=["stand", "policy_number", "species"],
                how="inner",
            )

            if not by_num_species.empty:
                rows.append(by_num_species)

    # 3. stand + policy_number when unique within stand
    meta_counts = (
        meta.groupby(["stand", "policy_number"], dropna=False)
        .size()
        .reset_index(name="n")
    )

    unique_meta = meta.merge(
        meta_counts[meta_counts["n"] == 1][["stand", "policy_number"]],
        on=["stand", "policy_number"],
        how="inner",
    )

    by_num = raw.merge(
        unique_meta,
        on=["stand", "policy_number"],
        how="inner",
    )

    if not by_num.empty:
        rows.append(by_num)

    if rows:
        out = pd.concat(rows, ignore_index=True)
    else:
        return pd.DataFrame()

    # Clean duplicate matches.
    subset_cols = ["stand", "policy", "species"]

    if "source_variable" in out.columns:
        subset_cols.append("source_variable")

    out = out.drop_duplicates(subset=subset_cols, keep="first")

    final_cols = [
        "species",
        "stand",
        "policy",
        "x_value",
        "area_ha",
        "initial_age",
        "final_age",
        "equation_id",
        "site_index",
        "zone",
        "source_variable",
    ]

    for col in final_cols:
        if col not in out.columns:
            out[col] = None

    out = out[final_cols].copy()
    out["selected"] = True

    return out


def _extract_xij_from_model(
    model,
    output=None,
    resumen=None,
    bosque=None,
    equation_metadata=None,
    tol=1e-6,
):
    """
    Extracts only selected x_ij assignments and corrects their metadata using
    resumen_c as the source of truth.

    Returns only selected policies, not all binary variables.
    """
    import pandas as pd

    policy_meta = _build_policy_metadata(
        resumen=resumen,
        bosque=bosque,
        equation_metadata=equation_metadata,
    )

    raw_model = _raw_selected_xij_from_model(model, tol=tol)
    raw_output = _selected_xij_from_output(output, tol=tol)

    raw_parts = []

    if raw_model is not None and not raw_model.empty:
        raw_parts.append(raw_model)

    if raw_output is not None and not raw_output.empty:
        raw_parts.append(raw_output)

    if not raw_parts:
        return pd.DataFrame()

    raw = pd.concat(raw_parts, ignore_index=True).drop_duplicates()

    selected = _join_selected_xij_with_resumen(raw, policy_meta)

    if selected.empty:
        # Last fallback: return raw selected values without metadata.
        selected = raw.copy()
        selected["species"] = selected.get("species_guess", None)
        selected["policy"] = selected.get("policy_raw", None)
        selected["selected"] = True

    selected = selected.drop_duplicates(
        subset=["species", "stand", "policy"],
        keep="first",
    ).reset_index(drop=True)

    selected = selected.sort_values(["species", "stand", "policy"]).reset_index(drop=True)

    return selected


def _extract_vt_from_model(model, output=None):
    import pandas as pd
    from pyomo.environ import value

    records = []

    candidate_names = [
        "harvest_volume",
        "v_t",
        "vt",
        "v",
    ]

    for name in candidate_names:
        comp = getattr(model, name, None)

        if comp is None:
            continue

        try:
            is_indexed = comp.is_indexed()
        except Exception:
            is_indexed = True

        try:
            if is_indexed:
                for idx in comp:
                    try:
                        val = value(comp[idx], exception=False)

                        if val is None:
                            continue

                        if isinstance(idx, tuple):
                            period = idx[0]
                        else:
                            period = idx

                        records.append(
                            {
                                "period": period,
                                "harvest_volume": float(val),
                                "source_variable": name,
                            }
                        )
                    except Exception:
                        continue
            else:
                val = value(comp, exception=False)
                if val is not None:
                    records.append(
                        {
                            "period": None,
                            "harvest_volume": float(val),
                            "source_variable": name,
                        }
                    )
        except Exception:
            continue

        if records:
            break

    if not records and output is not None:
        vt = output.get("total_harvest_per_period", None)

        if vt is not None:
            for period, val in enumerate(vt, start=1):
                records.append(
                    {
                        "period": period,
                        "harvest_volume": float(val),
                        "source_variable": "total_harvest_per_period",
                    }
                )

    vt_df = pd.DataFrame(records)

    if not vt_df.empty:
        vt_df = vt_df.sort_values("period").reset_index(drop=True)

    return vt_df


def _normalize_colname(name):
    return (
        str(name)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace(".", "_")
    )


def _find_column(df, candidates):
    normalized = {_normalize_colname(c): c for c in df.columns}

    for cand in candidates:
        key = _normalize_colname(cand)
        if key in normalized:
            return normalized[key]

    return None


def _first_non_null(series):
    series = series.dropna()

    if len(series) == 0:
        return None

    return series.iloc[0]


def _policy_metadata_from_bosque(bosque):
    import pandas as pd

    dfs = []

    for obj in bosque:
        if isinstance(obj, pd.DataFrame) and not obj.empty:
            dfs.append(obj.copy())

    if not dfs:
        return pd.DataFrame()

    raw = pd.concat(dfs, ignore_index=True)

    species_col = _find_column(
        raw,
        ["species", "especie", "sp", "tipo_especie"],
    )
    stand_col = _find_column(
        raw,
        ["stand", "rodal", "rodal_id", "id_rodal", "stand_id", "rodal_name"],
    )
    policy_col = _find_column(
        raw,
        ["policy", "politica", "política", "prescription", "management_policy"],
    )
    site_index_col = _find_column(
        raw,
        ["site_index", "siteindex", "site index", "si", "is", "indice_sitio", "índice_sitio"],
    )
    zone_col = _find_column(
        raw,
        ["zone", "zona", "z", "geographical_zone", "geographic_zone", "growth_zone", "zona_geografica", "zona_geográfica"],
    )

    if stand_col is None and policy_col is None:
        return pd.DataFrame()

    out = pd.DataFrame()

    out["species"] = raw[species_col].astype(str) if species_col is not None else None
    out["stand"] = raw[stand_col].astype(str) if stand_col is not None else None
    out["policy"] = raw[policy_col].astype(str) if policy_col is not None else None
    out["site_index"] = raw[site_index_col] if site_index_col is not None else None
    out["zone"] = raw[zone_col] if zone_col is not None else None

    group_cols = [c for c in ["species", "stand", "policy"] if c in out.columns]

    if not group_cols:
        return pd.DataFrame()

    meta = (
        out.groupby(group_cols, dropna=False)
        .agg(
            site_index=("site_index", _first_non_null),
            zone=("zone", _first_non_null),
        )
        .reset_index()
    )

    return meta


def _merge_xij_with_metadata(xij_df, bosque):
    if xij_df is None or xij_df.empty:
        return xij_df

    xij = xij_df.copy()

    for col in ["species", "stand", "policy"]:
        if col in xij.columns:
            xij[col] = xij[col].astype(str)

    meta = _policy_metadata_from_bosque(bosque)

    if meta.empty:
        return xij

    for col in ["species", "stand", "policy"]:
        if col in meta.columns:
            meta[col] = meta[col].astype(str)

    merge_cols = []

    for col in ["stand", "policy"]:
        if col in xij.columns and col in meta.columns:
            merge_cols.append(col)

    if not merge_cols:
        return xij

    meta_cols = merge_cols + [c for c in ["site_index", "zone"] if c in meta.columns]
    meta = meta[meta_cols].drop_duplicates(subset=merge_cols)

    xij = xij.merge(meta, on=merge_cols, how="left")

    return xij


def _write_single_model_txt(path, row, xij_df, vt_df=None):
    selected = xij_df[xij_df["selected"] == True].copy() if xij_df is not None and not xij_df.empty else xij_df

    with open(path, "w", encoding="utf-8") as f:
        f.write("treemun-sim optimization result\n")
        f.write("=" * 72 + "\n\n")

        f.write("Model metadata\n")
        f.write("-" * 72 + "\n")

        for key, value_ in row.items():
            f.write(f"{key}: {value_}\n")

        f.write("\nSelected stand-policy assignments\n")
        f.write("-" * 72 + "\n")

        if selected is None or selected.empty:
            f.write("No selected x_ij values were found.\n")
        else:
            cols = [c for c in ["species", "stand", "policy", "x_value", "site_index", "zone"] if c in selected.columns]
            f.write(selected[cols].to_string(index=False))
            f.write("\n")

        f.write("\nHarvest volume by period, v_t\n")
        f.write("-" * 72 + "\n")

        if vt_df is None or vt_df.empty:
            f.write("No v_t values were found.\n")
        else:
            cols = [c for c in ["period", "harvest_volume", "source_variable"] if c in vt_df.columns]
            f.write(vt_df[cols].to_string(index=False))
            f.write("\n")


def _save_front_run(
    front_df,
    solution_records,
    bosque,
    front_type,
    resumen=None,
    equation_metadata=None,
    results_dir="treemun_results",
    run_name=None,
    fig=None,
    save_plot=True,
    plot_filename=None,
    plot_dpi=300,
):
    import json
    import pandas as pd
    from pathlib import Path
    from datetime import datetime

    base_dir = Path(results_dir)

    if run_name is None:
        run_name = f"{front_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    run_name = _sanitize_filename(run_name)

    run_dir = base_dir / run_name
    per_model_dir = run_dir / "per_model"

    run_dir.mkdir(parents=True, exist_ok=True)
    per_model_dir.mkdir(parents=True, exist_ok=True)

    front_csv_path = run_dir / f"{front_type}_front_results.csv"
    front_txt_path = run_dir / f"{front_type}_front_summary.txt"

    _safe_to_csv(front_df, front_csv_path, index=False)

    plot_path = None

    if save_plot and fig is not None:
        if plot_filename is None:
            plot_filename = f"{front_type}_front.png"

        plot_path = run_dir / plot_filename
        fig.savefig(plot_path, dpi=plot_dpi, bbox_inches="tight")

    selected_xij = []
    all_vt = []

    for rec in solution_records:
        row = rec.get("row", {})
        model = rec.get("model", None)
        output = rec.get("output", None)

        model_id = row.get("model_id", rec.get("model_id", "model"))
        model_label = row.get("model_label", str(model_id))
        safe_label = _sanitize_filename(model_label)

        if model is None:
            xij_df = pd.DataFrame()
            vt_df = pd.DataFrame()
        else:
            xij_df = _extract_xij_from_model(model, output=output, resumen=resumen, bosque=bosque, equation_metadata=equation_metadata)
            vt_df = _extract_vt_from_model(model, output=output)

        xij_df = _merge_xij_with_metadata(xij_df, bosque)

        if not xij_df.empty:
            xij_df.insert(0, "model_id", model_id)
            xij_df.insert(1, "model_label", model_label)
            selected_xij.append(xij_df.copy())

        if not vt_df.empty:
            vt_df.insert(0, "model_id", model_id)
            vt_df.insert(1, "model_label", model_label)
            all_vt.append(vt_df)

        txt_path = per_model_dir / f"{safe_label}.txt"
        xij_csv_path = per_model_dir / f"{safe_label}_selected_policies.csv"
        vt_csv_path = per_model_dir / f"{safe_label}_vt.csv"

        _write_single_model_txt(txt_path, row, xij_df, vt_df=vt_df)

        _safe_to_csv(xij_df, xij_csv_path, index=False)
        _safe_to_csv(vt_df, vt_csv_path, index=False)

    selected_xij_df = pd.concat(selected_xij, ignore_index=True) if selected_xij else pd.DataFrame()
    all_vt_df = pd.concat(all_vt, ignore_index=True) if all_vt else pd.DataFrame()

    selected_xij_path = run_dir / "selected_policies_all_models.csv"
    all_vt_path = run_dir / "harvest_volume_per_period_all_models.csv"

    _safe_to_csv(selected_xij_df, selected_xij_path, index=False)
    _safe_to_csv(all_vt_df, all_vt_path, index=False)

    stats_paths = {}

    if not selected_xij_df.empty:
        n_models_solved = selected_xij_df["model_id"].nunique()

        policy_cols = [c for c in ["species", "policy"] if c in selected_xij_df.columns]

        if policy_cols:
            policy_freq = (
                selected_xij_df.groupby(policy_cols, dropna=False)
                .agg(
                    n_selected_assignments=("selected", "size"),
                    n_unique_stands=("stand", "nunique") if "stand" in selected_xij_df.columns else ("selected", "size"),
                    n_models=("model_id", "nunique"),
                )
                .reset_index()
            )

            policy_freq["model_share"] = policy_freq["n_models"] / max(n_models_solved, 1)

            policy_freq_path = run_dir / "policy_selection_frequency.csv"
            _safe_to_csv(policy_freq, policy_freq_path, index=False)
            stats_paths["policy_selection_frequency"] = str(policy_freq_path)

        stand_cols = [c for c in ["species", "stand", "policy", "site_index", "zone"] if c in selected_xij_df.columns]

        if stand_cols:
            stand_freq = (
                selected_xij_df.groupby(stand_cols, dropna=False)
                .agg(
                    n_selected=("selected", "size"),
                    n_models=("model_id", "nunique"),
                )
                .reset_index()
            )

            stand_freq_path = run_dir / "stand_policy_assignment_frequency.csv"
            _safe_to_csv(stand_freq, stand_freq_path, index=False)
            stats_paths["stand_policy_assignment_frequency"] = str(stand_freq_path)

        for attr in ["site_index", "zone"]:
            if attr in selected_xij_df.columns and selected_xij_df[attr].notna().any():
                group_cols = [attr]

                if "species" in selected_xij_df.columns:
                    group_cols = ["species"] + group_cols

                attr_summary = (
                    selected_xij_df.groupby(group_cols, dropna=False)
                    .agg(
                        n_selected_assignments=("selected", "size"),
                        n_unique_stands=("stand", "nunique") if "stand" in selected_xij_df.columns else ("selected", "size"),
                        n_models=("model_id", "nunique"),
                    )
                    .reset_index()
                )

                attr_summary["model_share"] = attr_summary["n_models"] / max(n_models_solved, 1)

                attr_path = run_dir / f"{attr}_selection_summary.csv"
                _safe_to_csv(attr_summary, attr_path, index=False)
                stats_paths[f"{attr}_selection_summary"] = str(attr_path)

    if not all_vt_df.empty:
        vt_summary = (
            all_vt_df.groupby("period", dropna=False)
            .agg(
                mean_harvest_volume=("harvest_volume", "mean"),
                min_harvest_volume=("harvest_volume", "min"),
                max_harvest_volume=("harvest_volume", "max"),
                std_harvest_volume=("harvest_volume", "std"),
                n_models=("model_id", "nunique"),
            )
            .reset_index()
        )

        vt_summary_path = run_dir / "harvest_volume_summary_by_period.csv"
        _safe_to_csv(vt_summary, vt_summary_path, index=False)
        stats_paths["harvest_volume_summary_by_period"] = str(vt_summary_path)

    with open(front_txt_path, "w", encoding="utf-8") as f:
        f.write("treemun-sim decision-support front summary\n")
        f.write("=" * 72 + "\n\n")
        f.write(f"front_type: {front_type}\n")
        f.write(f"run_name: {run_name}\n")
        f.write(f"n_models: {len(front_df)}\n")
        f.write(f"n_solved: {int(front_df['solved'].sum()) if 'solved' in front_df else 'NA'}\n")
        f.write(f"front_results_csv: {front_csv_path}\n")
        f.write(f"selected_policies_csv: {selected_xij_path}\n")
        f.write(f"harvest_volume_per_period_csv: {all_vt_path}\n")

        if plot_path is not None:
            f.write(f"front_plot_png: {plot_path}\n")

        f.write("\nFront DataFrame\n")
        f.write("-" * 72 + "\n")
        f.write(front_df.to_string(index=False))
        f.write("\n\n")

        if stats_paths:
            f.write("Additional statistics files\n")
            f.write("-" * 72 + "\n")
            for key, path_ in stats_paths.items():
                f.write(f"{key}: {path_}\n")

    metadata = {
        "front_type": front_type,
        "run_name": run_name,
        "run_dir": str(run_dir),
        "front_results_csv": str(front_csv_path),
        "front_summary_txt": str(front_txt_path),
        "selected_policies_csv": str(selected_xij_path),
        "harvest_volume_per_period_csv": str(all_vt_path),
        "front_plot_png": str(plot_path) if plot_path is not None else None,
        "stats_paths": stats_paths,
    }

    metadata_path = run_dir / "metadata.json"

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"Results saved to: {run_dir}")

    return metadata


def build_weighted_pareto_front(
    bosque,
    a_i_j_T,
    a_i_j_t,
    carbon_i_j_t,
    horizon,
    weights=None,
    pine_revenue=9,
    eucalyptus_revenue=10,
    min_ending_biomass=30000,
    discount_rate=0.08,
    even_flow_tolerance=0.0,
    solver_name="cbc",
    executable_path=None,
    gap=0.01,
    tee=False,
    make_plot=True,
    annotate_points=True,
    identify_knee=True,
    keep_dominated=True,
    save_results=False,
    results_dir="treemun_results",
    run_name=None,
    save_plot=True,
    plot_dpi=300,
    resumen=None,
    equation_metadata=None,
):
    import pandas as pd

    if weights is None:
        weights = [i / 10 for i in range(11)]

    rows = []
    solution_records = []

    for idx, w_npv in enumerate(weights):
        w_npv = float(w_npv)

        if w_npv < 0.0 or w_npv > 1.0:
            raise ValueError("All weights must be between 0 and 1.")

        w_carbon = 1.0 - w_npv

        model_id = idx
        model_label = f"weighted_wNPV_{w_npv:.4f}_wC_{w_carbon:.4f}"

        model = forest_management_optimization_model(
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
            objective="weighted",
            npv_weight=w_npv,
            carbon_weight=w_carbon,
        )

        results = _solve_model_compat(
            model,
            solver_name=solver_name,
            executable_path=executable_path,
            gap=gap,
            tee=tee,
        )

        output = extract_results(model, results)

        if output is None:
            row = {
                "model_id": model_id,
                "model_label": model_label,
                "weight_npv": w_npv,
                "weight_carbon": w_carbon,
                "objective_value": None,
                "npv_value": None,
                "carbon_seq_value": None,
                "even_flow_tolerance": even_flow_tolerance,
                "solver_status": str(results.solver.status),
                "termination_condition": str(results.solver.termination_condition),
                "solved": False,
            }
        else:
            row = {
                "model_id": model_id,
                "model_label": model_label,
                "weight_npv": w_npv,
                "weight_carbon": w_carbon,
                "objective_value": output.get("objective_value"),
                "npv_value": output.get("npv_value"),
                "carbon_seq_value": output.get("carbon_seq_value"),
                "even_flow_tolerance": output.get("even_flow_tolerance", even_flow_tolerance),
                "solver_status": str(results.solver.status),
                "termination_condition": str(results.solver.termination_condition),
                "solved": True,
            }

        rows.append(row)
        solution_records.append(
            {
                "model_id": model_id,
                "model": model,
                "output": output,
                "row": row,
            }
        )

    pareto_df = pd.DataFrame(rows)

    pareto_df["is_nondominated"] = False
    pareto_df["is_knee"] = False

    solved_mask = pareto_df["solved"] == True

    if solved_mask.any():
        solved_df = pareto_df.loc[solved_mask].copy()

        nondominated_mask = _is_nondominated_2d(
            solved_df,
            x_col="npv_value",
            y_col="carbon_seq_value",
        )

        nondominated_indices = solved_df.index[nondominated_mask]
        pareto_df.loc[nondominated_indices, "is_nondominated"] = True

        if identify_knee and len(nondominated_indices) > 0:
            nondominated_df = pareto_df.loc[nondominated_indices].copy()

            knee_idx = _identify_knee_by_ideal_distance(
                nondominated_df,
                x_col="npv_value",
                y_col="carbon_seq_value",
            )

            if knee_idx is not None:
                pareto_df.loc[knee_idx, "is_knee"] = True

    if not keep_dominated:
        pareto_df = pareto_df[pareto_df["is_nondominated"]].copy()

    fig = None
    ax = None

    if make_plot or (save_results and save_plot):
        fig, ax = plot_weighted_pareto_front(
            pareto_df,
            annotate_points=annotate_points,
            identify_knee=identify_knee,
        )

    if save_results:
        metadata = _save_front_run(
            front_df=pareto_df,
            solution_records=solution_records,
            bosque=bosque,
            front_type="weighted_pareto",
            results_dir=results_dir,
            run_name=run_name,
            fig=fig,
            save_plot=save_plot,
            plot_filename="weighted_pareto_front.png",
            plot_dpi=plot_dpi,
            resumen=resumen,
            equation_metadata=equation_metadata,
        )

        pareto_df.attrs["saved_results_dir"] = metadata["run_dir"]
        pareto_df.attrs["front_plot_png"] = metadata["front_plot_png"]

    return pareto_df, fig, ax


def plot_weighted_pareto_front(pareto_df, annotate_points=True, identify_knee=True):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 6))

    solved = pareto_df[pareto_df["solved"] == True].copy()
    nondom = solved[solved["is_nondominated"] == True].copy()
    dom = solved[solved["is_nondominated"] == False].copy()

    if not dom.empty:
        ax.scatter(
            dom["npv_value"].to_numpy(),
            dom["carbon_seq_value"].to_numpy(),
            marker="x",
            label="Dominated solutions",
        )

    if not nondom.empty:
        nondom = nondom.sort_values("npv_value")

        ax.plot(
            nondom["npv_value"].to_numpy(),
            nondom["carbon_seq_value"].to_numpy(),
            marker="o",
            label="Non-dominated weighted solutions",
        )

    if identify_knee:
        knee = solved[solved["is_knee"] == True]

        if not knee.empty:
            ax.scatter(
                knee["npv_value"].to_numpy(),
                knee["carbon_seq_value"].to_numpy(),
                marker="*",
                s=180,
                label="Knee point",
            )

    if annotate_points:
        for _, row in solved.iterrows():
            ax.annotate(
                f"w={row['weight_npv']:.2f}",
                (row["npv_value"], row["carbon_seq_value"]),
                textcoords="offset points",
                xytext=(5, 5),
                fontsize=8,
            )

    ax.set_xlabel("Net present value")
    ax.set_ylabel("Operational net carbon stock change (Mg C)")
    ax.set_title("Weighted Pareto front: NPV vs. carbon stock change")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()

    return fig, ax


def _normalize_epsilon_objective_name(name):
    if name is None:
        return None

    if not isinstance(name, str):
        raise TypeError("Objective names must be strings: 'npv' or 'carbon'.")

    key = name.strip().lower()

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

    if key not in aliases:
        raise ValueError(
            "Objective name must be 'npv' or 'carbon'. "
            f"Got {name!r}."
        )

    return aliases[key]


def _build_epsilon_values(
    epsilons,
    n_epsilons,
    epsilon_mode,
    epsilon_on,
    out_npv,
    out_carbon,
):
    import numpy as np

    epsilon_mode = epsilon_mode.strip().lower()

    if epsilon_mode not in {"absolute", "relative"}:
        raise ValueError("epsilon_mode must be 'absolute' or 'relative'.")

    if n_epsilons < 2:
        raise ValueError("n_epsilons must be at least 2.")

    npv_best = float(out_npv["npv_value"])
    carbon_at_npv = float(out_npv["carbon_seq_value"])

    npv_at_carbon = float(out_carbon["npv_value"])
    carbon_best = float(out_carbon["carbon_seq_value"])

    if epsilon_mode == "absolute":
        if epsilons is not None:
            if isinstance(epsilons, int):
                raise TypeError(
                    "epsilons must be a list of thresholds. "
                    "Use n_epsilons=... when you want an automatic grid."
                )

            epsilon_values = [float(eps) for eps in epsilons]
            epsilon_relative = [None for _ in epsilon_values]

            return epsilon_values, epsilon_relative

        if epsilon_on == "carbon":
            eps_low = min(carbon_at_npv, carbon_best)
            eps_high = max(carbon_at_npv, carbon_best)
        elif epsilon_on == "npv":
            eps_low = min(npv_at_carbon, npv_best)
            eps_high = max(npv_at_carbon, npv_best)
        else:
            raise RuntimeError("Invalid epsilon_on configuration.")

        epsilon_values = np.linspace(eps_low, eps_high, n_epsilons).tolist()
        epsilon_relative = [None for _ in epsilon_values]

        return epsilon_values, epsilon_relative

    if epsilon_on != "npv":
        raise ValueError(
            "epsilon_mode='relative' is currently supported for epsilon_on='npv'. "
            "For carbon thresholds, use epsilon_mode='absolute'."
        )

    if abs(npv_best) < 1e-12:
        raise ValueError("Cannot use relative NPV epsilons because maximum NPV is zero.")

    if epsilons is None:
        lower_fraction = npv_at_carbon / npv_best
        lower_fraction = max(0.0, min(1.0, lower_fraction))
        relative_values = np.linspace(lower_fraction, 1.0, n_epsilons).tolist()
    else:
        relative_values = [float(eps) for eps in epsilons]

    for eps in relative_values:
        if eps < 0.0 or eps > 1.0:
            raise ValueError(
                "Relative epsilons must be between 0 and 1. "
                "For example, 0.90 means at least 90% of maximum NPV."
            )

    epsilon_values = [eps * npv_best for eps in relative_values]

    return epsilon_values, relative_values


def build_epsilon_constraint_front(
    bosque,
    a_i_j_T,
    a_i_j_t,
    carbon_i_j_t,
    horizon,
    epsilons=None,
    n_epsilons=11,
    primary_objective="npv",
    epsilon_on=None,
    epsilon_mode="absolute",
    pine_revenue=9,
    eucalyptus_revenue=10,
    min_ending_biomass=30000,
    discount_rate=0.08,
    even_flow_tolerance=0.0,
    solver_name="cbc",
    executable_path=None,
    gap=0.01,
    tee=False,
    make_plot=True,
    annotate_points=True,
    identify_knee=True,
    keep_dominated=True,
    save_results=False,
    results_dir="treemun_results",
    run_name=None,
    save_plot=True,
    plot_dpi=300,
    resumen=None,
    equation_metadata=None,
):
    import pandas as pd
    from pyomo.environ import Constraint, Param

    if carbon_i_j_t is None:
        raise ValueError(
            "carbon_i_j_t is required to build an epsilon-constraint front."
        )

    primary_objective = _normalize_epsilon_objective_name(primary_objective)

    if epsilon_on is None:
        epsilon_on = "carbon" if primary_objective == "npv" else "npv"
    else:
        epsilon_on = _normalize_epsilon_objective_name(epsilon_on)

    if primary_objective == epsilon_on:
        raise ValueError(
            "primary_objective and epsilon_on must be different. "
            "Use either primary_objective='npv', epsilon_on='carbon' "
            "or primary_objective='carbon', epsilon_on='npv'."
        )

    model_npv = forest_management_optimization_model(
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
        objective="npv",
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
        raise RuntimeError(
            "Could not solve the pure NPV model needed to define epsilon bounds."
        )

    model_carbon = forest_management_optimization_model(
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
        objective="carbon",
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
        raise RuntimeError(
            "Could not solve the pure carbon model needed to define epsilon bounds."
        )

    epsilon_values, epsilon_relative = _build_epsilon_values(
        epsilons=epsilons,
        n_epsilons=n_epsilons,
        epsilon_mode=epsilon_mode,
        epsilon_on=epsilon_on,
        out_npv=out_npv,
        out_carbon=out_carbon,
    )

    rows = []
    solution_records = []

    for idx, eps in enumerate(epsilon_values):
        eps = float(eps)
        eps_rel = epsilon_relative[idx] if epsilon_relative is not None else None

        if epsilon_on == "npv" and eps_rel is not None:
            model_label = f"epsilon_max_{primary_objective}_NPV_{100 * eps_rel:.1f}pct"
        else:
            model_label = f"epsilon_max_{primary_objective}_{epsilon_on}_{idx:03d}"

        model_id = idx

        model = forest_management_optimization_model(
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
            objective=primary_objective,
        )

        model.epsilon_value = Param(initialize=eps)

        if epsilon_on == "carbon":
            model.epsilon_constraint = Constraint(
                expr=model.carbon_seq_value >= model.epsilon_value
            )
        elif epsilon_on == "npv":
            model.epsilon_constraint = Constraint(
                expr=model.npv_value >= model.epsilon_value
            )
        else:
            raise RuntimeError("Invalid epsilon_on configuration.")

        results = _solve_model_compat(
            model,
            solver_name=solver_name,
            executable_path=executable_path,
            gap=gap,
            tee=tee,
        )

        output = extract_results(model, results)

        if output is None:
            row = {
                "model_id": model_id,
                "model_label": model_label,
                "primary_objective": primary_objective,
                "epsilon_on": epsilon_on,
                "epsilon_mode": epsilon_mode,
                "epsilon_value": eps,
                "epsilon_relative": eps_rel,
                "objective_value": None,
                "npv_value": None,
                "carbon_seq_value": None,
                "even_flow_tolerance": even_flow_tolerance,
                "solver_status": str(results.solver.status),
                "termination_condition": str(results.solver.termination_condition),
                "solved": False,
            }
        else:
            row = {
                "model_id": model_id,
                "model_label": model_label,
                "primary_objective": primary_objective,
                "epsilon_on": epsilon_on,
                "epsilon_mode": epsilon_mode,
                "epsilon_value": eps,
                "epsilon_relative": eps_rel,
                "objective_value": output.get("objective_value"),
                "npv_value": output.get("npv_value"),
                "carbon_seq_value": output.get("carbon_seq_value"),
                "even_flow_tolerance": output.get("even_flow_tolerance", even_flow_tolerance),
                "solver_status": str(results.solver.status),
                "termination_condition": str(results.solver.termination_condition),
                "solved": True,
            }

        rows.append(row)
        solution_records.append(
            {
                "model_id": model_id,
                "model": model,
                "output": output,
                "row": row,
            }
        )

    epsilon_df = pd.DataFrame(rows)

    epsilon_df["is_nondominated"] = False
    epsilon_df["is_knee"] = False

    solved_mask = epsilon_df["solved"] == True

    if solved_mask.any():
        solved_df = epsilon_df.loc[solved_mask].copy()

        nondominated_mask = _is_nondominated_2d(
            solved_df,
            x_col="npv_value",
            y_col="carbon_seq_value",
        )

        nondominated_indices = solved_df.index[nondominated_mask]
        epsilon_df.loc[nondominated_indices, "is_nondominated"] = True

        if identify_knee and len(nondominated_indices) > 0:
            nondominated_df = epsilon_df.loc[nondominated_indices].copy()

            knee_idx = _identify_knee_by_ideal_distance(
                nondominated_df,
                x_col="npv_value",
                y_col="carbon_seq_value",
            )

            if knee_idx is not None:
                epsilon_df.loc[knee_idx, "is_knee"] = True

    if not keep_dominated:
        epsilon_df = epsilon_df[epsilon_df["is_nondominated"]].copy()

    fig = None
    ax = None

    if make_plot or (save_results and save_plot):
        fig, ax = plot_epsilon_constraint_front(
            epsilon_df,
            annotate_points=annotate_points,
            identify_knee=identify_knee,
        )

    if save_results:
        metadata = _save_front_run(
            front_df=epsilon_df,
            solution_records=solution_records,
            bosque=bosque,
            front_type="epsilon_constraint",
            results_dir=results_dir,
            run_name=run_name,
            fig=fig,
            save_plot=save_plot,
            plot_filename="epsilon_constraint_front.png",
            plot_dpi=plot_dpi,
            resumen=resumen,
            equation_metadata=equation_metadata,
        )

        epsilon_df.attrs["saved_results_dir"] = metadata["run_dir"]
        epsilon_df.attrs["front_plot_png"] = metadata["front_plot_png"]

    return epsilon_df, fig, ax


def plot_epsilon_constraint_front(epsilon_df, annotate_points=True, identify_knee=True):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 6))

    solved = epsilon_df[epsilon_df["solved"] == True].copy()
    nondom = solved[solved["is_nondominated"] == True].copy()
    dom = solved[solved["is_nondominated"] == False].copy()

    if not dom.empty:
        ax.scatter(
            dom["npv_value"].to_numpy(),
            dom["carbon_seq_value"].to_numpy(),
            marker="x",
            label="Dominated solutions",
        )

    if not nondom.empty:
        nondom = nondom.sort_values("npv_value")

        ax.plot(
            nondom["npv_value"].to_numpy(),
            nondom["carbon_seq_value"].to_numpy(),
            marker="o",
            label="Non-dominated epsilon-constraint solutions",
        )

    if identify_knee:
        knee = solved[solved["is_knee"] == True]

        if not knee.empty:
            ax.scatter(
                knee["npv_value"].to_numpy(),
                knee["carbon_seq_value"].to_numpy(),
                marker="*",
                s=180,
                label="Knee point",
            )

    if annotate_points:
        for _, row in solved.iterrows():
            if row["epsilon_on"] == "npv":
                rel = row.get("epsilon_relative", None)

                if rel is not None and rel == rel:
                    label = f"NPV ≥ {100 * rel:.0f}%"
                else:
                    label = f"εNPV={row['epsilon_value']:.0f}"
            else:
                label = f"εC={row['epsilon_value']:.0f}"

            ax.annotate(
                label,
                (row["npv_value"], row["carbon_seq_value"]),
                textcoords="offset points",
                xytext=(5, 5),
                fontsize=8,
            )

    ax.set_xlabel("Net present value")
    ax.set_ylabel("Operational net carbon stock change (Mg C)")

    if not solved.empty:
        primary = solved["primary_objective"].iloc[0]
        eps_on = solved["epsilon_on"].iloc[0]
        title = (
            "Epsilon-constraint Pareto front: "
            f"maximize {primary.upper()} subject to {eps_on.upper()} threshold"
        )
    else:
        title = "Epsilon-constraint Pareto front"

    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()

    return fig, ax

# ---------------------------------------------------------------------
# End decision-support front utilities
# ---------------------------------------------------------------------


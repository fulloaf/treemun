# treemun/treemun_sim/optimization.py
"""
Optimization module for treemun forest management models.
Provides functions to create, solve, and extract results from a forest optimization model example.
"""

from pyomo.environ import *
from pyomo.opt import SolverFactory
import os

def forest_management_optimization_model(bosque, a_i_j_T, a_i_j_t, horizon, 
                                       pine_revenue=9, eucalyptus_revenue=10, 
                                       min_ending_biomass=30000, discount_rate=0.08):
    """
    Creates and returns a forest management optimization model using Pyomo.
    
    Args:
        bosque (List[pd.DataFrame]): List of forest simulation DataFrames, each representing 
                                   a stand-policy combination with temporal dynamics
        a_i_j_T (Dict): Dictionary with final standing biomass (at the end of the planning horizon)
                                values by stand-policy combination, structure: {(stand_id, policy): biomass_value}
        a_i_j_t (Dict): Dictionary with harvestable biomass coefficients by period of thinning/harvest respectively,
                       structure: {(period, species, policy, stand_id): biomass_value}
        horizon (int): Planning horizon in years
        pine_revenue (float or List[float]): biomass revenue for pine species ($/m³). 
                                         Can be a single value (constant revenue) or 
                                         a list of length horizon (variable revenue by period)
        eucalyptus_revenue (float or List[float]): biomass revenue for eucalyptus species ($/m³). 
                                               Can be a single value or list of length horizon
        min_ending_biomass (float): Minimum total standing biomass required at end of horizon (m³)
        discount_rate (float): Annual discount rate for NPV calculation (decimal, e.g., 0.08 = 8%)
    
    Returns:
        model (ConcreteModel): Configured Pyomo optimization model ready for solving
    """
    
    # Validate and convert revenue to arrays
    if isinstance(pine_revenue, (int, float)):
        pine_revenue_array = [pine_revenue] * horizon
    else:
        pine_revenue_array = list(pine_revenue)
        if len(pine_revenue_array) != horizon:
            raise ValueError(f"pine_revenue must have length {horizon}, got {len(pine_revenue_array)}")
    
    if isinstance(eucalyptus_revenue, (int, float)):
        eucalyptus_revenue_array = [eucalyptus_revenue] * horizon
    else:
        eucalyptus_revenue_array = list(eucalyptus_revenue)
        if len(eucalyptus_revenue_array) != horizon:
            raise ValueError(f"eucalyptus_revenue must have length {horizon}, got {len(eucalyptus_revenue_array)}")
    
    # Extract sets from forest simulation data
    I_pino = set()
    I_euca = set()
    J_pino = set()
    J_euca = set()

    for df in bosque:
        # Extract stand IDs by species
        pinus_df = df[df["Especie"] == "Pinus"]
        I_pino.update(pinus_df['id_rodal'].unique())
        
        euca_df = df[df["Especie"] == "Eucapyltus"]
        I_euca.update(euca_df['id_rodal'].unique())
        
        # Extract policies by species
        for policy in df['politica'].unique():
            if 'pino' in policy:
                J_pino.add(policy)
            elif 'eucalyptus' in policy:
                J_euca.add(policy)

    # Create Pyomo model
    model = ConcreteModel()

    # Define sets
    model.I_pino = Set(initialize=sorted(I_pino))
    model.I_euca = Set(initialize=sorted(I_euca))
    model.J_pino = Set(initialize=sorted(J_pino))
    model.J_euca = Set(initialize=sorted(J_euca))
    model.T = RangeSet(1, horizon)
    model.Epino = Set(initialize=["Pinus"])
    model.Eeuca = Set(initialize=["Eucapyltus"])

    # Economic parameters (indexed by period for variable revenue)
    model.pine_revenue = Param(model.T, initialize={t: pine_revenue_array[t-1] for t in model.T})
    model.eucalyptus_revenue = Param(model.T, initialize={t: eucalyptus_revenue_array[t-1] for t in model.T})
    model.min_ending_biomass = Param(initialize=min_ending_biomass)
    model.discount_rate = Param(initialize=discount_rate)

    # Define valid stand-policy combinations
    valid_pino_indices = [(i, j) for i in model.I_pino for j in model.J_pino 
                          if any((t, e, j, i) in a_i_j_t for t in model.T for e in model.Epino)]

    valid_euca_indices = [(i, j) for i in model.I_euca for j in model.J_euca
                          if any((t, e, j, i) in a_i_j_t for t in model.T for e in model.Eeuca)]

    # Decision variables
    model.x_pine = Var(valid_pino_indices, within=Binary)
    model.x_eucalyptus = Var(valid_euca_indices, within=Binary)
    model.harvest_volume = Var(model.T, within=NonNegativeReals)

    # Objective function: Maximize Net Present Value
    def objective_rule(model):
        pine_npv = sum(
            a_i_j_t[(t, e, j, i)] * model.x_pine[i, j] * model.pine_revenue[t] / (1 + model.discount_rate)**t
            for t in model.T for e in model.Epino for j in model.J_pino for i in model.I_pino
            if (i, j) in valid_pino_indices and (t, e, j, i) in a_i_j_t
        )
        
        eucalyptus_npv = sum(
            a_i_j_t[(t, e, j, i)] * model.x_eucalyptus[i, j] * model.eucalyptus_revenue[t] / (1 + model.discount_rate)**t
            for t in model.T for e in model.Eeuca for j in model.J_euca for i in model.I_euca
            if (i, j) in valid_euca_indices and (t, e, j, i) in a_i_j_t
        )
        
        return pine_npv + eucalyptus_npv

    model.objective = Objective(rule=objective_rule, sense=maximize)

    # Constraint: Single policy assignment per stand
    def single_assignment_pine_rule(model, i):
        return sum(model.x_pine[i, j] for j in model.J_pino if (i, j) in valid_pino_indices) == 1

    def single_assignment_eucalyptus_rule(model, i):
        return sum(model.x_eucalyptus[i, j] for j in model.J_euca if (i, j) in valid_euca_indices) == 1

    model.single_assignment_pine = Constraint(model.I_pino, rule=single_assignment_pine_rule)
    model.single_assignment_eucalyptus = Constraint(model.I_euca, rule=single_assignment_eucalyptus_rule)

    # Constraint: Track harvest volumes by period
    def harvest_volume_tracking_rule(model, t):
        return sum(
            a_i_j_t[(t, e, j, i)] * model.x_pine[i, j]
            for e in model.Epino for j in model.J_pino for i in model.I_pino
            if (t, e, j, i) in a_i_j_t
        ) + sum(
            a_i_j_t[(t, e, j, i)] * model.x_eucalyptus[i, j]
            for e in model.Eeuca for j in model.J_euca for i in model.I_euca
            if (t, e, j, i) in a_i_j_t
        ) == model.harvest_volume[t]

    model.harvest_volume_tracking = Constraint(model.T, rule=harvest_volume_tracking_rule)

    # Constraint: Even-flow (non-decreasing harvest volumes)
    def even_flow_rule(model, t):
        if t < model.T.last():
            return model.harvest_volume[t + 1] >= model.harvest_volume[t]
        else:
            return Constraint.Skip

    model.even_flow = Constraint(model.T, rule=even_flow_rule)

    # Constraint: Minimum ending forest inventory
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
    
    Args:
        model (Pyomo Model): The optimization model after being solved.
        results (Pyomo Results object): The results object from the solver.
        
    Returns:
        dict: A dictionary containing the objective value, the harvest vector, lists of 
              pine and eucalyptus stand assignments, and their respective counts. 
              Returns None if no solution was found.
    """
    # Check if the solver found an optimal or feasible solution
    term_cond = results.solver.termination_condition
    if term_cond == TerminationCondition.optimal or term_cond == TerminationCondition.feasible:
        
        # Extract the Objective Function Value
        objective_value = value(model.objective)
        
        # Build the harvest vector
        harvest_vector = [model.harvest_volume[t].value for t in model.T]
        
        # Get coordinates for x_pine where the value is greater than zero
        # A small tolerance is used to avoid floating-point precision issues.
        xpino_values = [(i, j) for (i, j) in model.x_pine if model.x_pine[i, j].value > 1e-6]
        
        # Get coordinates for x_eucalyptus where the value is greater than zero
        xeuca_values = [(i, j) for (i, j) in model.x_eucalyptus if model.x_eucalyptus[i, j].value > 1e-6]
        
        # Package everything into a dictionary for a clean and organized return
        output_data = {
            'objective_value': objective_value,
            'total_harvest_per_period': harvest_vector,
            'pinus_stand_plan': xpino_values,
            'total_pinus_stand_treated': len(xpino_values),
            'eucalyptus_stand_plan': xeuca_values,
            'total_eucalyptus_stand_treated': len(xeuca_values)
        }
        
        return output_data
        
    else:
        print(f"\nAn optimal solution was not found. Termination condition: {term_cond}")
        return None





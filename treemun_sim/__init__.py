"""Treemün: dry-wood trajectory simulation and forest planning."""

from .carbon import (
    CO2E_FACTOR,
    DEFAULT_SPECIES_CARBON_PARAMETERS,
    SpeciesCarbonParameter,
    StandingWoodCarbonAccounting,
    add_carbon_accounting,
)
from .compatibility import convert_v1_stand_file
from .core import DEFAULT_RANDOM_SEED, simulate_forest
from .economic import (
    ECONOMIC_METRIC_BY_MODE,
    VALID_ECONOMIC_MODES,
    EconomicEvaluation,
    evaluate_forest_economics,
)
from .data import load_lookup_table, load_stand_table
from .optimization import (
    biobjective_normalization_from_payoff,
    build_biobjective_payoff_table,
    build_epsilon_constraint_front,
    build_forest_management_model,
    build_three_objective_epsilon_front,
    build_three_objective_payoff_table,
    build_weighted_pareto_front,
    filter_nondominated_points,
    identify_three_objective_knee_point,
    extract_solution,
    forest_management_optimization_model,
    solve_model,
)
from .simulation import (
    DEFAULT_EUCALYPTUS_POLICIES,
    DEFAULT_FALLBACK_THINNING_FRACTION,
    DEFAULT_MINIMUM_CURVE_RESIDUAL_FRACTION,
    DEFAULT_PINUS_POLICIES,
    EUCALYPTUS,
    PINUS,
)
from .spatial import (
    export_optimal_solution_to_geopackage,
    export_simulation_to_geopackage,
    forest_to_long_table,
)
from .spatial_constraints import (
    add_final_harvest_adjacency,
    add_greenup_adjacency,
    add_spatial_conflict_measure,
    add_greenup_event_conflict_measure,
    build_adjacency_edges,
    build_final_harvest_indicator,
    count_greenup_adjacency_conflicts,
    count_greenup_event_conflicts,
)

__version__ = "2.0.0"
__author__ = "Felipe Ulloa-Fierro"

__all__ = [
    "CO2E_FACTOR",
    "DEFAULT_EUCALYPTUS_POLICIES",
    "DEFAULT_FALLBACK_THINNING_FRACTION",
    "DEFAULT_MINIMUM_CURVE_RESIDUAL_FRACTION",
    "DEFAULT_PINUS_POLICIES",
    "DEFAULT_RANDOM_SEED",
    "DEFAULT_SPECIES_CARBON_PARAMETERS",
    "EUCALYPTUS",
    "ECONOMIC_METRIC_BY_MODE",
    "EconomicEvaluation",
    "VALID_ECONOMIC_MODES",
    "evaluate_forest_economics",
    "PINUS",
    "SpeciesCarbonParameter",
    "StandingWoodCarbonAccounting",
    "add_carbon_accounting",
    "add_final_harvest_adjacency",
    "add_greenup_adjacency",
    "add_spatial_conflict_measure",
    "add_greenup_event_conflict_measure",
    "biobjective_normalization_from_payoff",
    "build_adjacency_edges",
    "build_biobjective_payoff_table",
    "build_final_harvest_indicator",
    "build_epsilon_constraint_front",
    "build_forest_management_model",
    "build_three_objective_epsilon_front",
    "build_three_objective_payoff_table",
    "build_weighted_pareto_front",
    "convert_v1_stand_file",
    "count_greenup_adjacency_conflicts",
    "count_greenup_event_conflicts",
    "export_optimal_solution_to_geopackage",
    "export_simulation_to_geopackage",
    "extract_solution",
    "filter_nondominated_points",
    "identify_three_objective_knee_point",
    "forest_management_optimization_model",
    "forest_to_long_table",
    "load_lookup_table",
    "load_stand_table",
    "simulate_forest",
    "solve_model",
]

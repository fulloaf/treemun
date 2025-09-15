# treemun/treemun_sim/__init__.py
"""
treemun - Package for simulation of forest growth, yield and management

basic usage example:

    import treemun_sim as tm
    
    horizon=30
    stand_number=100
    
    # Forest simulation
    forest, forest_summary, last_period_biomass, collected_biomass = tm.simular_bosque(
        horizonte=horizon,
        num_rodales=stand_number
    )
    
    # Optimization
    model = tm.forest_management_optimization_model(
        forest, last_period_biomass, collected_biomass, horizon
    )
    
    results = tm.solve_model(model, 'cbc')
    solution = tm.extract_results(model, results)
    
"""

# Main functions for simulation
from .core import simular_bosque

# Optimization functions
from .optimization import (
    forest_management_optimization_model,
    solve_model,
    extract_results
)

__version__ = "1.1.5"
__author__ = "Felipe Ulloa-Fierro"

# Main functions exposed by the package
__all__ = [
    # Simulation
    "simular_bosque",
    
    # Optimization
    "forest_management_optimization_model",
    "solve_model", 
    "extract_results"
]
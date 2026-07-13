# treemun/treemun_sim/__init__.py

"""
treemun - Package for simulation of forest growth, yield and management

basic usage example:

    import treemun as tm

    horizon = 30
    stand_number = 100

    # Forest simulation
    forest, forest_summary, last_period_biomass, collected_biomass = tm.simular_bosque(
        horizonte=horizon,
        num_rodales=stand_number
    )

    # Optional carbon post-processing
    forest, forest_summary, last_period_biomass, collected_biomass, carbon_seq = tm.simular_bosque(
        horizonte=horizon,
        num_rodales=stand_number,
        Carbon=True,
        return_carbon_opti=True
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
    extract_results,
)

# Carbon proxy functions
from .carbon import (
    CarbonSequestrationProxy,
    SpeciesCarbonParameter,
    DEFAULT_SPECIES_CARBON_PARAMETERS,
    CO2E_FACTOR,
    add_carbon_proxy_to_bosque,
    getCarbon4Opti,
)

# Spatial functions (optional - require geopandas)
try:
    from .spatial import (
        export_simulation_to_shapefile,
        export_optimal_policy_to_shapefile,
    )
    _SPATIAL_AVAILABLE = True
except ImportError:
    _SPATIAL_AVAILABLE = False

    # Define placeholder functions that inform users about missing dependencies
    def export_simulation_to_shapefile(*args, **kwargs):
        raise ImportError(
            "Funciones espaciales no disponibles. "
            "Instala las dependencias con: pip install treemun-sim[spatial]"
        )

    def export_optimal_policy_to_shapefile(*args, **kwargs):
        raise ImportError(
            "Funciones espaciales no disponibles. "
            "Instala las dependencias con: pip install treemun-sim[spatial]"
        )


__version__ = "1.4.0"
__author__ = "Felipe Ulloa-Fierro"

# Main functions exposed by the package
__all__ = [
    # Simulation
    "simular_bosque",

    # Optimization
    "forest_management_optimization_model",
    "solve_model",
    "extract_results",

    # Carbon proxy
    "CarbonSequestrationProxy",
    "SpeciesCarbonParameter",
    "DEFAULT_SPECIES_CARBON_PARAMETERS",
    "CO2E_FACTOR",
    "add_carbon_proxy_to_bosque",
    "getCarbon4Opti",

    # Spatial (optional)
    "export_simulation_to_shapefile",
    "export_optimal_policy_to_shapefile",

    # v1.4.0 spatial adjacency and green-up extensions
    "build_adjacency_edges",
    "build_final_harvest_indicator",
    "add_final_harvest_adjacency",
    "add_greenup_adjacency",
    "count_greenup_adjacency_conflicts",
    "build_multi_epsilon_front_3d",
    "plot_multi_epsilon_front_3d",
]
from .optimization import build_weighted_pareto_front, plot_weighted_pareto_front
from .optimization import build_epsilon_constraint_front, plot_epsilon_constraint_front

# ---------------------------------------------------------------------
# v1.4.0 spatial adjacency and green-up extensions
# ---------------------------------------------------------------------

try:
    from .spatial_adjacency import (
        build_adjacency_edges,
        build_final_harvest_indicator,
    )
except Exception:
    pass

try:
    from .adjacency_extension import (
        add_final_harvest_adjacency,
    )
except Exception:
    pass

try:
    from .greenup_extension import (
        add_greenup_adjacency,
        count_greenup_adjacency_conflicts,
    )
except Exception:
    pass

try:
    from .multi_epsilon import (
        build_multi_epsilon_front_3d,
        plot_multi_epsilon_front_3d,
    )
except Exception:
    pass

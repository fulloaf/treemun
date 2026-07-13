# Changelog

## Version 1.4.0

### Added
- Adjacency-aware harvest scheduling tools.
- Same-period adjacent final-harvest penalties.
- Generalized green-up adjacency windows through `greenup_window`.
- Optional hard green-up constraints and soft green-up penalties.
- Weighted spatial penalties based on shared boundary length.
- Multi-epsilon NPV-carbon-adjacency front generation.
- Knee-point identification for three-objective trade-off analysis.
- Clean example dataset with `examples/forest_stands.csv` and `examples/shapefile/treemun_landscape.*`.

### Changed
- Extended the carbon-aware v1.3.0 optimization framework with spatial regularization capabilities.
- Updated package version to 1.4.0.


# Changelog

All notable changes to treemun-sim will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2025-02-12

### Added
- **File loading functionality**: Load forest stands from CSV/TXT files instead of only random generation
  - New parameter `archivo_rodales` in `simular_bosque()`
  - New function `cargar_rodales_desde_archivo()` in generadores module
  - Automatic validation of stand configurations against lookup table
  - Support for both comma-separated (.csv) and tab-separated (.txt) files
  - Detailed error messages for invalid stand configurations
- **Species name flexibility**: Accept multiple variations (case-insensitive)
  - Pinus: 'Pinus', 'PINUS', 'pinus', 'Pino'
  - Eucalyptus: 'Eucalyptus', 'EUCALYPTUS', 'eucalyptus', 'Eucapyltus', 'Eucalipto'
- **Spatial analysis module** (optional): `spatial.py` for shapefile integration
  - `export_simulation_to_shapefile()`: Export simulation results with biomass attributes (format: bio_P[N]_t[T])
  - `export_optimal_policy_to_shapefile()`: Export optimal management policy
  - Requires optional dependency: `pip install treemun-sim[spatial]`
  - GeoPandas and Shapely added as optional dependencies
- **Example files**:
  - CSV example: `examples/example_100stands_plantation.csv` (100 stands)
  - Shapefile examples: 100-stand landscape with geometries
  - Documentation: `examples/README_SPATIAL_ANALYSIS.md`
- **Enhanced documentation**:
  - Comprehensive file loading guide in README
  - Spatial analysis workflow examples
  - API reference updates

### Fixed
- **Infinite loop bug**: Fixed issue when passing only 1 policy per species
  - Changed minimum feasible policies requirement from 2 to 1 in `generar_rodales_aleatorios()`
- **Pandas FutureWarning**: Updated `stack()` calls to use `future_stack=True` parameter in simulacion.py

### Changed
- **Validation strictness**: Only Pinus equation IDs [21, 22, 25, 26, 29, 30] are accepted for initial stand loading
- **Backward compatibility**: 100% maintained - existing code using `num_rodales` works unchanged
- setup.py: Added `[spatial]` and updated `[complete]` extras_require options

## [1.1.5] - 2024-09-15

### Added
- Initial PyPI release
- Forest growth simulation for Pinus radiata and Eucalyptus globulus
- Multiple configurable management policies
- Random forest landscape generation
- Forest management optimization model
- Support for CBC and CPLEX solvers
- Comprehensive documentation and examples

[1.2.0]: https://github.com/fulloaf/treemun/compare/v1.1.5...v1.2.0
[1.1.5]: https://github.com/fulloaf/treemun/releases/tag/v1.1.5
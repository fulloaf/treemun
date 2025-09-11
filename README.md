# treemun: a growth and yield simulator for chilean plantation forest

[![PyPI version](https://badge.fury.io/py/treemun-sim.svg)](https://badge.fury.io/py/treemun-sim)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python package that implements a discrete-time simulation framework for evaluating management policies in Pinus radiata and Eucalyptus globulus forest stands.

- Forest growth simulation for Pinus and Eucalyptus species
- Multiple configurable management policies
- Biomass calculation using allometric equations
- Random forest landscape generation (instance building)
- Data preparation for optimization algorithms
- Guaranteed reproducibility through seeds

## Installation

```bash
pip install treemun-sim
```

## Basic Usage

```python
import treemun_sim as tm

# Simulation with default parameters
forest, summary, final_biomass, estimated_biomass = tm.simular_bosque()

print(f"Generated {len(forest)} stand-policy combinations")
print(f"Total optimization data points: {len(estimated_biomass)}")
```

## Advanced Usage

```python
import treemun_sim as tm

# Custom simulation
forest, summary, final_biomass, estimated_biomass = tm.simular_bosque(
    policies_pino=[(9, 18), (10, 20), (11, 22)],  # (thinning, harvest)
    policies_eucalyptus=[(9,), (10,), (11,)],     # (harvest,)
    horizonte=25,
    num_rodales=50,
    semilla=1234
)

# Results analysis
for i, df in enumerate(forest[:3]):  # First 3 stands
    print(f"Stand {i+1}:")
    print(f"  - Species: {df['Especie'].iloc[0]}")
    print(f"  - Policy: {df['politica'].iloc[0]}")
    print(f"  - Final biomass: {df['biomasa'].iloc[-1]:.2f} tons")
```

## Input Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `policies_pino` | `List[Tuple[int, int]]` | 16 policies | Pine policies: `[(thinning_age, harvest_age), ...]` |
| `policies_eucalyptus` | `List[Tuple[int]]` | 4 policies | Eucalyptus policies: `[(harvest_age,), ...]` |
| `horizonte` | `int` | 30 | Time horizon in years |
| `num_rodales` | `int` | 100 | Number of stands to generate |
| `semilla` | `int` | 5555 | Seed for reproducibility |

## Output Data

| Output | Type | Description |
|--------|------|-------------|
| `forest` | `List[pd.DataFrame]` | Period-by-period simulation for each stand-policy combination |
| `summary` | `List[Dict]` | Summary information for each stand |
| `final_biomass` | `Dict` | Biomass at the end of horizon per stand-policy |
| `estimated_biomass` | `Dict` | Biomass for each stand (by species) applying each policy in each time period |

## Supported Species

### Pinus
- **Policies**: Thinning + Harvest
- only remember: Thinning age < harvest ages 
- **Default policies**: 16 combinations -> one-to-one combination of [thinning ages: 9-12 years ; harvest ages: 18-24 years]

### Eucalyptus
- **Policies**: Harvest only
- **Harvest ages**: any year.
- **Default policies**: 4 options -> [9-12 years]

## Data Structure

### Forest DataFrame
Each element in `forest` contains:
- `periodo`: Time period (1 to horizonte)
- `edad_rodal`: Stand age in each period
- `biomasa`: Total biomass in tons
- `bioOPT`: biomass collected in tons (it consider only thinned and harvested biomass amounts)
- `condición`: Management status ("sin manejo" (no managed) / "con manejo" (managed))
- `kitral_class`: Kitral classification
- `politica`: Applied policy identifier

### Optimization Dictionary
`estimated_biomass` has the structure:
```python
{
    (period, (stand_id, policy, species)): biomass_value,
    ...
}
```

## Use Cases

- **Forest research**: Analysis of different management strategies
- **Optimization**: Input for mathematical programming algorithms
- **Planning**: Long-term scenario evaluation
- **Education**: Teaching forest management concepts

## Contributing

Contributions are welcome. To contribute:

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Author

**Felipe Ulloa-Fierro**
- Email: felipe.ulloa@utalca.cl
- Institution: Universidad de Talca

## Citation

If you use TreeMun in your research, you can cite it as:

```
Ulloa-Fierro, F. (2025). TreeMun: A Growth and Yield Simulator for Chilean Plantation Forest. 
Python Package Version 1.0.0. https://pypi.org/project/treemun-sim/
```

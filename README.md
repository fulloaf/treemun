# Treemun: a growth and yield simulator for Chilean plantation forest

[![PyPI version](https://badge.fury.io/py/treemun-sim.svg)](https://badge.fury.io/py/treemun-sim)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/treemun-sim?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads)](https://pepy.tech/projects/treemun-sim)

A Python package that implements a discrete-time simulation framework for evaluating management policies in Pinus radiata and Eucalyptus globulus forest stands, with integrated optimization capabilities for forest management planning.

**Key Features:**
- Forest growth simulation for Pinus and Eucalyptus species
- Multiple configurable management policies
- Total aereal biomass calculation using allometric equations (based on Miranda et al. (2023) report)
- Random forest landscape generation (instance building)
- Includes a forest management optimization model example
- Support for multiple optimization solvers
- Data preparation for optimization algorithms
- Guaranteed reproducibility through seeds

## Tool Objectives

- Simulate forest stand-level biomass growth dynamics across multi-decadal planning horizons for *Pinus radiata* and *Eucalyptus globulus* species.
- Enable comparison of silvicultural strategies through automated generation of multiple stand-policy combinations to evaluate the biological/economic yield of each forest stand.
- Provide a decision support framework for tactical/strategic forest management planning, creating a seamless workflow from biological growth modeling to prescriptive management optimization.
- Deliver an accessible computational tool that reduces technical barriers to applying operations research methodologies in forest management context, supporting both research and educational applications.


## Simulator's Empirical Foundation

The growth models implemented in this system are founded upon comprehensive field data from Chilean forest plantations, documented by Hernández et al. (2011) and Corvalán et al. (2012). The subsequent analytical work of Miranda et al. (2023) establishes the technical and theoretical guidelines for the present tool, which focuses specifically on two species: *Pinus radiata* and *Eucalyptus globulus*.

### Forest Stand Classification

The table below summarizes the set of species-specific ecological and management dimensions for the considered forest stands, whose values (state-parameters) served as a basis for adjusting parameters for the mathematical foundation of the growth model.

| Dimension | *Pinus radiata* | *Eucalyptus globulus* |
|-----------|-----------------|------------------------|
| **Geographic Zone** | Z6-Z7 | Z01-Z02 |
| **Site Index** | 23, 26, 29, 32 | 24, 26, 28, 30, 32 |
| **Management Regime** | Pulpable, Multipurpose, Intensive 1 or 2 | Unmanaged |
| **Stand Condition** | Managed | Unmanaged |
| **Initial Density** | 1250 trees/ha | 800, 1250 trees/ha |

#### Understanding the Classification Dimensions

- **Site Index (SI):** The average height of the dominant trees at a base age of 10 years. It is calculated from the total height of the 100 trees per hectare with the largest DBH (Diameter at Breast Height, measured at 1.3 m above ground level).

- **Management Regime:** The management scheme applied to the stand, which can be one of the following:
  - **Pulpable:** A regime involving thinning to waste (pre-commercial thinning).
  - **Multipurpose:** A regime where the stand has been pruned and thinned twice.
  - **Intensive 1:** A regime where the stand has been pruned three times and thinned twice.
  - **Intensive 2:** A regime where the stand has been pruned two or three times and thinned twice, depending on site quality.
  - **Unmanaged:** When none of the above regimes are applied.

- **Stand Condition:** The state of the forest stand relative to its management history.

- **Initial Density:** The initial number of trees per hectare in the forest stand at age 0 (at the time of planting).

## Simulator's Mathematical Foundation

The simulator is functionally grounded in the forest stand-level biomass prediction model developed by Miranda et al. (2023), whose structure was selected through rigorous nonlinear least squares fitting using the Levenberg-Marquardt algorithm.

### Core Growth Equation

The general growth equation models stand total biomass as a function of stand age:
```
B_t^s = [α · (E_t^s)^β + γ] · A^s
```

Where:
- **B_t^s**: Total aerial biomass (m³) of forest stand s in time period t.
- **E_t^s**: Biological age of forest stand s in time period t.
- **α, β, γ**: Model coefficients that vary based on forest stand characteristics.
- **A^s**: Area of forest stand s (ha).

The specific coefficient values for each specie, zone, initial density, site index (SI), management type and condition are provided in the appendix tables.

## Simulation Logic

![Simulation_logic_scheme](https://raw.githubusercontent.com/fulloaf/treemun/main/docs/images/growth_schemes_new.jpg)

### Species-Specific Management Policies

**Pinus radiata** stands follow a dual-curve growth model:

- **State 0** (pre-thinning): `B_t = f(E_t, α₁, β₁, γ₁, A)` for t ≤ thinning-age
- **State 1** (post-thinning): `B_t = f(E_t, α₂, β₂, γ₂, A)` for thinning-age < t ≤ harvest-age

**Eucalyptus globulus** stands use a single continuous growth curve: `B_t = f(E_t, α, β, γ, A)` with management determined solely by harvest age.

### Regeneration Cycle

Following any harvest, the model assumes immediate replanting, resetting the stand's biological age to 1 in the subsequent period.

### Simulation Period vs Biological Age

- **Simulation Period (t)**: Discrete time steps of the planning horizon, where t ∈ {1, 2, ..., H}
- **Stand Biological Age (E)**: Physiological age of trees, evolves as:
```
E^s(t) = initial_age_s + t - 1  (if no harvest)
E^s(t) = t - t_last_harvest      (if harvested)
```

## Growth Simulation Examples

### Pinus radiata Example
11.65 ha stand over 30-year horizon with thinning at age 12 (t=10) and harvest at age 24 (t=22).

![Pinus radiata growth simulation](https://raw.githubusercontent.com/fulloaf/treemun/main/docs/images/grafico_final_tesis_equations_pino.svg)

### Eucalyptus globulus Example
17.88 ha stand over 30-year horizon with harvests at 10-year intervals (t=1, 11, 21).

![Eucalyptus globulus growth simulation](https://raw.githubusercontent.com/fulloaf/treemun/main/docs/images/grafico_final_tesis_equations_eucalipto.svg)


## Mathematical Model

The optimization module implements a Mixed-Integer Linear Programming (MILP) model for strategic forest management planning, extending Johnson and Scheurman's (1977) Model I formulation to address multi-species plantation management.

**Problem Formulation**

The model addresses the landscape-level forest management problem where a heterogeneous forest landscape is partitioned into a set I of management units (stands) that can be managed using different policies j ∈ J over a planning horizon T. The objective is to determine the optimal policy assignment for each stand to maximize the **Net Present Value (NPV)** of biomass collection while ensuring sustainability and even-flow constraints.

**Decision Variables and Parameters**

**Decision Variables:**

- *x<sub>ij</sub>*: Binary variable indicating whether policy *j* is assigned to stand *i* (*x<sub>ij</sub>* = 1 if assigned, 0 otherwise)
- *v<sub>t</sub>*: Auxiliary continuous variable tracking total biomass collected in period *t*

**Parameters:**
- *a<sub>ijt</sub>*: Biomass collected from stand *i* under policy *j* in period *t* (m³)
- *a<sub>ij</sub><sup>T</sup>*: Standing biomass in stand *i* under policy *j* at the end of planning horizon (m³)
- *r<sup>t</sup>*: Biomass revenue in period *t* ($/m³)
- *τ*: Annual discount rate
- *B*: Minimum required standing biomass at planning horizon end (m³)


### Model Formulation

0. **Objective Function** (NPV Maximization):
   $$\text{maximize } \sum_{i \in I} \sum_{j \in J} \sum_{t \in T} \frac{r^t \cdot a_{ijt} \cdot x_{ij}}{(1+\tau)^t}$$

**Subject to:**

1. **Single Policy Assignment Constraint:**
   $$\sum_{j \in J} x_{ij} = 1 \quad \forall i \in I$$

2. **Biomass Collection Tracking:**
   $$\sum_{i \in I} \sum_{j \in J} a_{ijt} \cdot x_{ij} = v_t \quad \forall t \in T$$

3. **Even-Flow Constraint** (Non-decreasing harvest):
   $$v_{t+1} \geq v_t \quad \forall t \in T \setminus \{|T|\}$$

4. **Sustainability Constraint:**
   $$\sum_{i \in I} \sum_{j \in J} a_{ij}^T \cdot x_{ij} \geq B$$

5. **Variable Domains:**
   $$x_{ij} \in \{0,1\} \quad \forall i \in I, j \in J$$
   $$v_t \geq 0 \quad \forall t \in T$$

This formulation seek to identify landscape’s policy plan that maximizes the NPV across the planning horizon (Eq. 0) considering that: (i) at most one policy j is selected for each stand i (Eq. 1), (ii) the biomass collected is non-decreasing over time, therefore the biomass collected in period t + 1 must be at least as much as in period t (Eqs. 2 & 3), and (iii) at the end of the planning horizon, a minimum total amount of standing biomass (defined as B) is guaranteed (Eq. 4). The last restriction (Eq. 5) refers to the nature of the variables. 

## Installation

### Basic Installation
```bash
pip install treemun-sim
```

### Installation with Optimization Solvers
```bash
# With free CBC solver (recommended)
pip install treemun-sim[solvers]

# With commercial solvers (requires licenses)
pip install treemun-sim[solvers-extended]

# Complete installation with development tools
pip install treemun-sim[complete]
```

### Solver Requirements
- **CBC**: ✅ Included with `[solvers]` installation
- **CPLEX**: Requires IBM ILOG CPLEX license

## Basic Usage

### Forest Simulation
```python
import treemun_sim as tm

# Simulation with default parameters
forest, summary, final_biomass, collected_biomass = tm.simular_bosque()

print(f"Generated {len(forest)} stand-policy combinations")
print(f"Total optimization data points: {len(collected_biomass)}")
```

### Forest Management Optimization
```python
import treemun_sim as tm

# Generate forest data

horizon = 15
num_stands = 100

forest, summary, final_biomass, collected_biomass = tm.simular_bosque(
    horizonte=horizon,
    num_rodales=num_stands
)

# Create optimization model
model = tm.forest_management_optimization_model(
    bosque=forest,
    a_i_j_T=final_biomass,
    a_i_j_t=collected_biomass,
    horizon=horizon,
    pine_revenue=12,           # $/m³
    eucalyptus_revenue=10,     # $/m³
    min_ending_biomass=25000,  # m³
    discount_rate=0.08         # 8% annual
)

# Solve model
results = tm.solve_model(model, solver_name='cbc', gap=0.01)

# Extract solution
solution = tm.extract_results(model, results)

if solution:
    print(f"Optimal NPV: ${solution['objective_value']:,.2f}")
    print(f"Pine stands managed: {solution['total_pinus_stand_treated']}")
    print(f"Pine stands planning: {solution['pinus_stand_plan']}")
    print(f"Eucalyptus stands managed: {solution['total_eucalyptus_stand_treated']}")
    print(f"Eucalyptus stands planning: {solution['eucalyptus_stand_plan']}")
    print("Total biomass collected per period:", solution['total_harvest_per_period'])
```

## Visual Examples

The following figures illustrate how different management policies affect biomass dynamics over time (30 years horizon) for representative stands:

### Pinus radiata Stand Simulation
![Pinus radiata policies](https://raw.githubusercontent.com/fulloaf/treemun/main/docs/images/grafico_final_policies_pino.svg)

The figure shows three management policies applied to a single Pinus radiata stand:
- **Policy 1**: Thinning at 12 years, harvest at 24 years (longer rotation)
- **Policy 2**: Thinning at 9 years, harvest at 18 years (intensive management)
- **Policy 3**: Thinning at 11 years, harvest at 20 years (intermediate strategy)

Each policy produces different biomass trajectories, affecting both total yield and temporal distribution of harvests.

### Eucalyptus globulus Stand Simulation
![Eucalyptus globulus policies](https://raw.githubusercontent.com/fulloaf/treemun/main/docs/images/grafico_final_policies_eucalipto.svg)

The figure demonstrates three harvest-only policies for an Eucalyptus globulus stand:
- **Policy 1**: 10-year rotations (frequent short rotations)
- **Policy 2**: 11-year rotations (moderate cycle)
- **Policy 3**: 12-year rotations (longer maturation period)

The visualization shows how rotation length affects cumulative biomass production and harvest timing across the planning horizon.

These examples demonstrate the package's capability to simulate complex stand dynamics under different management regimes, providing the foundation data for optimization models.

This framework's ability to model forest stand age progression, which incorporates post-harvest regeneration, also enables the annual tracking of each stand's fuel class. This dynamic assessment is based on the Chilean KITRAL fuel model  (Julio et al., 1997). The following table lists the specific fuel codes associated with each of the plantation forest species under consideration.

## KITRAL Fuel Classification

| Species | Age Range | Unmanaged | Managed |
|---------|-----------|-----------|---------|
| *Pinus radiata* | ≤ 3 | PL01 | - |
| *Pinus radiata* | 3 < age ≤ 11 | PL02 | PL05 |
| *Pinus radiata* | 11 < age ≤ 17 | PL03 | PL06 |
| *Pinus radiata* | > 17 | PL04 | PL07 |
| *Eucalyptus globulus* | ≤ 3 | PL08 | - |
| *Eucalyptus globulus* | 3 < age ≤ 10 | PL09 | - |
| *Eucalyptus globulus* | > 10 | PL10 | - |


## Advanced Usage

### Custom Simulation Parameters
```python
import treemun_sim as tm

# Custom simulation
forest, summary, final_biomass, collected_biomass = tm.simular_bosque(
    policies_pino=[(9, 18), (10, 20), (11, 22)],  # (thinning, harvest)
    policies_eucalyptus=[(9,), (10,), (11,)],     # (harvest,)
    horizonte=15,
    num_rodales=100,
    semilla=1234
)

# Results analysis
for i, df in enumerate(forest[:3]):  # First 3 stands
    print(f"Stand {i+1}:")
    print(f"  - Species: {df['Especie'].iloc[0]}")
    print(f"  - Policy: {df['politica'].iloc[0]}")
    print(f"  - Final biomass: {df['biomasa'].iloc[-1]:.2f} tons")
```

### Variable Revenue in Optimization
```python
# Variable revenue over time
pine_revenues = [10, 11, 12, 13, 14]  # Increasing revenues for 5-year horizon
eucalyptus_revenues = [8, 9, 10, 11, 12]

model = tm.forest_management_optimization_model(
    bosque=forest,
    a_i_j_T=final_biomass,
    a_i_j_t=collected_biomass,
    horizon=15,
    pine_revenue=pine_revenues,        # Variable revenue
    eucalyptus_revenue=eucalyptus_revenues,
    min_ending_biomass=25000,
    discount_rate=0.08
)
```

## API Reference

### Simulation Function

#### `simular_bosque()`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `policies_pino` | `List[Tuple[int, int]]` | 16 policies | Pine policies: `[(thinning_age, harvest_age), ...]` |
| `policies_eucalyptus` | `List[Tuple[int]]` | 4 policies | Eucalyptus policies: `[(harvest_age,), ...]` |
| `horizonte` | `int` | 30 | Time horizon in years |
| `num_rodales` | `int` | 100 | Number of stands to generate |
| `semilla` | `int` | 5555 | Seed for reproducibility |

### Optimization Functions

#### `forest_management_optimization_model()`

| Parameter | Type | Description |
|-----------|------|-------------|
| `bosque` | `List[pd.DataFrame]` | Forest simulation data |
| `a_i_j_T` | `Dict` | Final standing biomass by stand-policy |
| `a_i_j_t` | `Dict` | Harvestable biomass by period |
| `horizon` | `int` | Planning horizon in years |
| `pine_revenue` | `float` or `List[float]` | Pine biomass revenue ($/m³) |
| `eucalyptus_revenue` | `float` or `List[float]` | Eucalyptus biomass revenue ($/m³) |
| `min_ending_biomass` | `float` | Minimum final period biomass guaranteed |
| `discount_rate` | `float` | Annual discount rate for NPV |

#### `solve_model()`

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | `ConcreteModel` | Pyomo optimization model |
| `solver_name` | `str` | Solver name ('cbc', 'cplex') |
| `gap` | `float` | Relative optimality gap (default: 0.01) |
| `executable_path` | `str` | Path to solver executable (optional) |
| `tee` | `bool` | Display solver output (default: True) |

#### `extract_results()`

Returns a dictionary with:
- `objective_value`: Optimal NPV for the planning
- `total_harvest_per_period`: Schedule for collected biomass 
- `pinus_stand_plan`: Policy assignments for pine stands
- `eucalyptus_stand_plan`: Policy assignments for eucalyptus stands
- `total_pinus_stand_treated`: Count of pine stands
- `total_eucalyptus_stand_treated`: Count of eucalyptus stands

## Output Data Structure

### Forest DataFrame
Each element in `forest` contains:
- `periodo`: Time period (1 to horizonte)
- `edad_rodal`: Stand age in each period
- `biomasa`: Total biomass in tons
- `bioOPT`: biomass collected in tons (considers only thinned and harvested biomass amounts)
- `condición`: Management status ("sin manejo" (no managed) / "con manejo" (managed)
- `kitral_class`: Classification according to Kitral's System (Chilean fuel model)
- `politica`: Applied policy identifier 

### Optimization Dictionaries
`collected_biomass structure:
```python
{
    (period, species, policy, stand_id): biomass_value,
    ...
}
```

`final_biomass structure:
```python
{
    (stand_id, policy): biomass_value,
    ...
}
```

## Supported Species

### Pinus
- **Policies**: Thinning + Harvest
- **Constraint**: Thinning age < harvest age 
- **Default policies**: 16 combinations (thinning ages: 9-12 years; harvest ages: 18-24 years)

### Eucalyptus
- **Policies**: Harvest only
- **Harvest ages**: Any year
- **Default policies**: 4 options (9-12 years)

## Use Cases

- **Forest research**: Analysis of different management strategies
- **Tactical and Strategic planning**: Mid/Long-term forest management optimization
- **Sustainability assessment**: Balancing economic and ecological objectives
- **Policy evaluation**: Comparing management alternatives performances
- **Education**: Teaching forest management and optimization concepts

## Solver Installation Guide

### Free Solvers
```bash
# CBC (recommended - included with treemun-sim[solvers])
pip install pulp

```

### Commercial Solvers
```bash
# CPLEX (requires IBM license)
pip install cplex

```

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

## Reference

A. Miranda, B. Mola-Yudego, and V. Hinojosa. Stand-level biomass prediction models in Eucalyptus Globulus and Pinus Radiata plantations in south-central Chile. Technical report, University of Eastern Finland, September 2023.

Johnson, K. N., & Scheurman, H. L. (1977). Techniques for prescribing optimal timber harvest and investment under different objectives—discussion and synthesis. *Forest Science*, 23(suppl_1), a0001–z0001. https://doi.org/10.1093/FORESTSCIENCE/23.S1.A0001


## Citation

If you use Treemun in your research, you can cite it as:

```
Ulloa-Fierro, F. (2025). Treemun: A Growth and Yield Simulator for Chilean Plantation Forest. 
Python Package Version 1.1.5 https://pypi.org/project/treemun-sim/

```

## Acknowledgements

Author thanks to European Union’s Horizon 2020 Research and Innovation Programme under grant agreements Nos. 101037419–FIRE-RES and 101007950–DecisionES, and the support of National Agency for Research and Development (ANID, Chile) through the grant FONDECYT N.1220830, through the Complex Engineering Systems Institute PIA/PUENTE AFB230002.



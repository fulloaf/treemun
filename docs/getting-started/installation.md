# Installation

Treemün requires **Python 3.10 or later** and runs on Linux, macOS and Windows.

## With pip

=== "Simulation only"

    ```bash
    pip install treemun-sim
    ```

    Installs NumPy and pandas. Enough for simulation, economic evaluation and carbon accounting.

=== "Full workflow"

    ```bash
    pip install "treemun-sim[complete]"
    ```

    Adds Pyomo and the HiGHS solver (`highspy`) for optimization, and GeoPandas, Shapely and pyogrio for spatial work.

=== "Development"

    ```bash
    git clone https://github.com/fulloaf/treemun.git
    cd treemun
    pip install -e ".[complete,test,notebook]"
    ```

    Editable install with the test suite and the notebook dependencies (Matplotlib, Plotly, JupyterLab).

Using a virtual environment is recommended:

```bash
python -m venv treemun-env
source treemun-env/bin/activate      # Windows: treemun-env\Scripts\activate
pip install "treemun-sim[complete]"
```

### Optional extras

| Extra | Installs | Needed for |
|---|---|---|
| `optimization` | `pyomo`, `highspy` | building and solving harvest-scheduling models |
| `spatial` | `geopandas`, `shapely`, `pyogrio` | adjacency, green-up constraints, GeoPackage export |
| `complete` | `optimization` + `spatial` | the full workflow |
| `cplex` | `pyomo`, `cplex` | IBM CPLEX through its Python API |
| `notebook` | `matplotlib`, `plotly`, `scipy`, `jupyterlab`, … | running the example and benchmark notebooks |
| `test` | `pytest` and the optional dependencies | running the test suite |

## With Conda

The repository includes two environment files.

```bash
conda env create -f environment.yml        # CBC + HiGHS
conda activate treemun200
```

```bash
conda env create -f environment-cplex.yml  # CBC + HiGHS + IBM CPLEX runtime
conda activate treemun200-cplex
```

Both install Treemün in editable mode from the cloned repository, with the test and notebook dependencies.

## Solvers

Optimization goes through [Pyomo](https://www.pyomo.org/), so any Pyomo-compatible MILP solver can be used. Pass its name to `solve_model` or to the `solver_name=` argument of the front builders.

| Solver | Name(s) | How to get it |
|---|---|---|
| HiGHS | `appsi_highs`, `highs` | included in the `optimization` and `complete` extras |
| CBC | `cbc` | `conda install -c conda-forge coincbc` (native executable, not a pip package) |
| CPLEX | `cplex`, `cplex_direct`, `cplex_persistent`, `appsi_cplex` | licensed executable in `PATH`, or the `cplex` extra (Community Edition size limits apply) |

`cbc` is the default in function signatures. If you installed only the pip extras, pass `"appsi_highs"` explicitly.

!!! tip "Solver runtime controls"
    `solve_model` translates common options to each solver's native settings:

    ```python
    results = tm.solve_model(
        model,
        "appsi_highs",
        relative_gap=0.01,        # MIP gap (default 1%)
        threads=8,                # None keeps the solver default
        time_limit_seconds=600,   # None means no limit
    )
    ```

    `threads` caps what the solver uses; it does not request CPUs from a cluster scheduler. The front builders accept the same settings as `solver_options={...}`.

## Check the installation

```python
import treemun_sim as tm
print(tm.__version__)

lookup = tm.load_lookup_table()
print(len(lookup), "growth equations")      # 34 growth equations
```

To check that a solver is visible to Pyomo:

```python
import pyomo.environ as pyo
print(pyo.SolverFactory("appsi_highs").available(exception_flag=False))
```

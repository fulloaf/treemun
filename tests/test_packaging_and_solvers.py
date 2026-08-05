from __future__ import annotations

import json
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_solver_dependencies_are_separated_by_installation_mode():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    extras = data["project"]["optional-dependencies"]

    assert "highspy>=1.7" in extras["optimization"]
    assert "highspy>=1.7" in extras["complete"]
    assert "cplex>=22.1.2" in extras["cplex"]
    assert all(not dependency.startswith("cplex") for dependency in extras["complete"])


def test_conda_environments_document_open_and_optional_commercial_solvers():
    open_environment = (ROOT / "environment.yml").read_text()
    cplex_environment = (ROOT / "environment-cplex.yml").read_text()

    assert "coincbc" in open_environment
    assert "highspy" in open_environment
    assert "cplex" not in open_environment

    assert "coincbc" in cplex_environment
    assert "highspy" in cplex_environment
    assert "cplex" in cplex_environment
    assert "ibmdecisionoptimization" in cplex_environment


def test_notebook_detects_cbc_highs_and_cplex():
    notebook = json.loads(
        (ROOT / "examples" / "Treemun_2_0_0_full_105_stands_analysis.ipynb").read_text()
    )
    source = "\n".join(
        "".join(cell.get("source", [])) for cell in notebook["cells"]
    )
    for solver_name in ("cbc", "highs", "appsi_highs", "cplex"):
        assert f'"{solver_name}"' in source


def test_solver_runtime_option_keys_cover_supported_mip_solvers():
    from treemun_sim.optimization import _solver_runtime_option_keys

    assert _solver_runtime_option_keys("cplex") == {
        "relative_gap": "mipgap",
        "threads": "threads",
        "time_limit_seconds": "timelimit",
    }
    assert _solver_runtime_option_keys("highs") == {
        "relative_gap": "mip_rel_gap",
        "threads": "threads",
        "time_limit_seconds": "time_limit",
    }
    assert _solver_runtime_option_keys("cbc") == {
        "relative_gap": "ratioGap",
        "threads": "threads",
        "time_limit_seconds": "seconds",
    }


def test_native_solver_options_can_be_assigned_to_option_container():
    from treemun_sim.optimization import _set_solver_option

    class FakeSolver:
        def __init__(self):
            self.options = {}

    solver = FakeSolver()
    _set_solver_option(solver, "threads", 8)
    _set_solver_option(solver, "timelimit", 600.0)

    assert solver.options == {"threads": 8, "timelimit": 600.0}

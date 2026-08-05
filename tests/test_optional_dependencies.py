import importlib.util

import pytest

import treemun_sim as tm


def test_package_import_does_not_require_pyomo():
    assert tm.__version__ == "2.0.0"


def test_optimization_has_clear_optional_dependency_error():
    if importlib.util.find_spec("pyomo") is not None:
        pytest.skip("Pyomo is installed in this environment.")
    with pytest.raises(ImportError, match="Pyomo"):
        tm.build_forest_management_model(
            policy_summary=[],
            ending_dry_wood_by_policy={},
            harvested_dry_wood_by_period={},
            horizon=1,
        )

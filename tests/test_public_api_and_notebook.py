from pathlib import Path

import nbformat

import treemun_sim as tm


def test_multiobjective_public_api_is_exposed():
    expected = {
        "add_spatial_conflict_measure",
        "add_greenup_event_conflict_measure",
        "biobjective_normalization_from_payoff",
        "build_biobjective_payoff_table",
        "build_three_objective_epsilon_front",
        "build_three_objective_payoff_table",
        "filter_nondominated_points",
        "identify_three_objective_knee_point",
        "count_greenup_event_conflicts",
        "evaluate_forest_economics",
    }
    assert expected.issubset(set(tm.__all__))
    for name in expected:
        assert callable(getattr(tm, name))


def test_full_capability_notebook_has_valid_python_cells():
    project_root = Path(__file__).resolve().parents[1]
    notebook_path = (
        project_root / "examples" / "Treemun_2_0_0_full_105_stands_analysis.ipynb"
    )
    notebook = nbformat.read(notebook_path, as_version=4)
    assert len(notebook.cells) >= 40
    for index, cell in enumerate(notebook.cells):
        if cell.cell_type == "code":
            compile(cell.source, f"<notebook cell {index}>", "exec")


def test_payoff_normalization_and_nondominated_filter():
    import pandas as pd

    payoff = pd.DataFrame(
        {
            "npv_value": [100.0, 70.0],
            "carbon_stock_time_tC_year": [40.0, 90.0],
        }
    )
    normalization = tm.biobjective_normalization_from_payoff(payoff)
    assert normalization == {
        "npv_reference": 70.0,
        "carbon_reference": 40.0,
        "npv_scale": 30.0,
        "carbon_scale": 50.0,
    }

    points = pd.DataFrame(
        {
            "npv": [10.0, 9.0, 8.0, 10.0],
            "carbon": [5.0, 6.0, 4.0, 5.0],
            "conflicts": [2.0, 1.0, 3.0, 2.0],
        }
    )
    nondominated = tm.filter_nondominated_points(
        points,
        maximize_columns=("npv", "carbon"),
        minimize_columns=("conflicts",),
    )
    assert len(nondominated) == 2
    assert set(map(tuple, nondominated[["npv", "carbon", "conflicts"]].to_numpy())) == {
        (10.0, 5.0, 2.0),
        (9.0, 6.0, 1.0),
    }


def test_three_objective_knee_point_is_identified():
    import pandas as pd

    payoff = pd.DataFrame(
        {
            "optimized_for": [
                "economic",
                "carbon",
                "greenup_event_conflicts",
            ],
            "economic_value": [100.0, 60.0, 75.0],
            "carbon_stock_time_tC_year": [40.0, 100.0, 70.0],
            "greenup_event_conflict_count": [20.0, 10.0, 2.0],
        }
    )
    front = pd.DataFrame(
        {
            "economic_value": [100.0, 88.0, 78.0, 60.0],
            "carbon_stock_time_tC_year": [40.0, 70.0, 82.0, 100.0],
            "greenup_event_conflict_count": [20.0, 9.0, 5.0, 10.0],
        }
    )
    result = tm.identify_three_objective_knee_point(
        front, payoff_table=payoff
    )
    assert result["is_knee_point"].sum() == 1
    assert {
        "normalized_economic_score",
        "normalized_carbon_score",
        "normalized_greenup_score",
        "knee_score",
    }.issubset(result.columns)
    assert result.attrs["knee_method"] in {
        "maximum_distance_from_anchor_hyperplane",
        "distance_to_ideal",
    }


def test_notebook_uses_all_stands_and_reduced_three_objective_grid():
    project_root = Path(__file__).resolve().parents[1]
    notebook_path = (
        project_root / "examples" / "Treemun_2_0_0_full_105_stands_analysis.ipynb"
    )
    notebook = nbformat.read(notebook_path, as_version=4)
    source = "\n".join(cell.source for cell in notebook.cells)
    assert "TRI_CARBON_POINTS = 3" in source
    assert "TRI_GREENUP_POINTS = 2" in source
    assert "TRI_DEMO_STAND_COUNT" not in source
    assert "reuse_payoff_anchors=True" in source
    assert "reuse_cached_solutions=True" in source
    assert '"solution_source"' in source
    assert '"threads": SOLVER_THREADS' in source
    assert "identify_three_objective_knee_point" in source
    assert "interactive_three_objective_front_with_knee.html" in source

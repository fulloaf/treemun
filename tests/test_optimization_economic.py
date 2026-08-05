import pandas as pd
import pytest

import treemun_sim as tm

pyo = pytest.importorskip("pyomo.environ")


def _inputs():
    forest = []
    summary = []
    ending = {}
    harvest = {}
    for policy, amount in (("policy_1", 100.0), ("policy_2", 50.0)):
        forest.append(
            pd.DataFrame(
                [
                    {
                        "period": 1,
                        "stand_id": "stand_1",
                        "policy": policy,
                        "species": tm.PINUS,
                        "area_ha": 10.0,
                        "operation": "final_harvest",
                        "harvested_dry_wood_t": amount,
                    }
                ]
            )
        )
        summary.append(
            {
                "stand_id": "stand_1",
                "species": tm.PINUS,
                "area_ha": 10.0,
                "initial_age": 10,
                "ending_age": 10,
                "policy": policy,
                "policy_number": 1,
                "thinning_age": None,
                "final_harvest_age": 10,
                "initial_equation_id": 1,
            }
        )
        ending[("stand_1", policy)] = 0.0
        harvest[(1, tm.PINUS, policy, "stand_1")] = amount
    return forest, summary, ending, harvest


def test_model_uses_gross_revenue_coefficients():
    forest, summary, ending, harvest = _inputs()
    model = tm.build_forest_management_model(
        policy_summary=summary,
        ending_dry_wood_by_policy=ending,
        harvested_dry_wood_by_period=harvest,
        horizon=1,
        forest=forest,
        economic_mode="gross_revenue",
        economic_parameters={"revenue_per_dry_t": 100.0},
        discount_rate=0.0,
        even_flow_mode="none",
        objective="economic",
    )
    assert model._treemun_metadata["economic_metric"] == "discounted_revenue"
    assert model._treemun_metadata["economic_coefficients"][("stand_1", "policy_1")] == pytest.approx(10_000.0)
    assert model._treemun_metadata["economic_coefficients"][("stand_1", "policy_2")] == pytest.approx(5_000.0)


def test_model_uses_detailed_npv_coefficients():
    forest, summary, ending, harvest = _inputs()
    model = tm.build_forest_management_model(
        policy_summary=summary,
        ending_dry_wood_by_policy=ending,
        harvested_dry_wood_by_period=harvest,
        horizon=1,
        forest=forest,
        economic_mode="detailed_cash_flow",
        economic_parameters={
            "revenue_per_dry_t": 100.0,
            "variable_cost_per_dry_t": 10.0,
            "final_harvest_cost_per_dry_t": 5.0,
            "replanting_cost_per_ha": 100.0,
        },
        discount_rate=0.0,
        even_flow_mode="none",
        objective="economic",
    )
    assert model._treemun_metadata["economic_metric"] == "net_present_value"
    # policy_1: 100*100 - 100*10 - 100*5 - 10*100 = 7,500
    assert model._treemun_metadata["economic_coefficients"][("stand_1", "policy_1")] == pytest.approx(7_500.0)


def test_terminal_stock_fraction_and_residual_value_are_supported():
    forest, summary, ending, harvest = _inputs()
    for trajectory in forest:
        trajectory["standing_dry_wood_t_before_operation"] = 200.0
        trajectory["standing_dry_wood_t_after_operation"] = 120.0
    ending[("stand_1", "policy_1")] = 120.0
    ending[("stand_1", "policy_2")] = 80.0

    model = tm.build_forest_management_model(
        policy_summary=summary,
        ending_dry_wood_by_policy=ending,
        harvested_dry_wood_by_period=harvest,
        horizon=1,
        forest=forest,
        economic_mode="detailed_cash_flow",
        economic_parameters={
            "revenue_per_dry_t": 0.0,
            "terminal_value_per_dry_t": 25.0,
        },
        discount_rate=0.0,
        minimum_ending_dry_wood_fraction=0.50,
        even_flow_mode="none",
        objective="economic",
    )
    assert model._treemun_metadata["initial_dry_wood_total_t"] == pytest.approx(
        200.0
    )
    assert pyo.value(model.minimum_ending_dry_wood_fraction.lower) == pytest.approx(
        100.0
    )
    assert model._treemun_metadata["economic_coefficients"][
        ("stand_1", "policy_1")
    ] == pytest.approx(3_000.0)
    assert model._treemun_metadata["model_build_time_seconds"] >= 0.0


def test_three_objective_front_reuses_payoff_anchors_without_solving():
    selected = pd.DataFrame(
        {
            "stand_id": ["stand_1"],
            "policy": ["policy_1"],
        }
    )
    payoff = pd.DataFrame(
        [
            {
                "optimized_for": "economic",
                "economic_mode": "detailed_cash_flow",
                "economic_metric": "net_present_value",
                "economic_value": 100.0,
                "npv_value": 100.0,
                "carbon_stock_time_tC_year": 10.0,
                "greenup_event_conflict_count": 5.0,
                "ending_dry_wood_t": 20.0,
                "selected_policies": selected,
            },
            {
                "optimized_for": "carbon",
                "economic_mode": "detailed_cash_flow",
                "economic_metric": "net_present_value",
                "economic_value": 60.0,
                "npv_value": 60.0,
                "carbon_stock_time_tC_year": 20.0,
                "greenup_event_conflict_count": 3.0,
                "ending_dry_wood_t": 40.0,
                "selected_policies": selected,
            },
            {
                "optimized_for": "greenup_event_conflicts",
                "economic_mode": "detailed_cash_flow",
                "economic_metric": "net_present_value",
                "economic_value": 80.0,
                "npv_value": 80.0,
                "carbon_stock_time_tC_year": 15.0,
                "greenup_event_conflict_count": 1.0,
                "ending_dry_wood_t": 30.0,
                "selected_policies": selected,
            },
        ]
    )

    front = tm.build_three_objective_epsilon_front(
        adjacency_edges=pd.DataFrame(),
        final_harvest_indicator={},
        carbon_epsilon_values=[10.0],
        greenup_event_conflict_epsilon_values=[5.0, 1.0],
        payoff_table=payoff,
        model_options={},
        solver_name="cbc",
        filter_nondominated=False,
    )

    assert len(front) == 2
    assert set(front["solution_source"]) == {
        "reused_economic_anchor",
        "reused_greenup_anchor",
    }
    assert front["number_of_solver_calls"].eq(0).all()
    assert front["solve_time_seconds"].eq(0.0).all()
    assert front.attrs["requested_combination_count"] == 2
    assert front.attrs["reused_model_count"] == 2
    assert front.attrs["solved_model_count"] == 0
    assert front.attrs["avoided_solver_calls"] == 2

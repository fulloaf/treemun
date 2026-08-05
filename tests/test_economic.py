import pandas as pd
import pytest

import treemun_sim as tm


def _example_trajectory() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "period": 1,
                "stand_id": "stand_1",
                "policy": "policy_1",
                "species": tm.PINUS,
                "area_ha": 10.0,
                "operation": "thinning",
                "harvested_dry_wood_t": 100.0,
            },
            {
                "period": 2,
                "stand_id": "stand_1",
                "policy": "policy_1",
                "species": tm.PINUS,
                "area_ha": 10.0,
                "operation": "final_harvest",
                "harvested_dry_wood_t": 200.0,
            },
        ]
    )


def test_gross_revenue_mode_uses_only_income():
    evaluation = tm.evaluate_forest_economics(
        [_example_trajectory()],
        economic_mode="gross_revenue",
        discount_rate=0.0,
        economic_parameters={"revenue_per_dry_t": 100.0},
    )
    assert evaluation.economic_metric == "discounted_revenue"
    assert evaluation.value_by_policy[("stand_1", "policy_1")] == pytest.approx(
        30_000.0
    )
    assert evaluation.summary_by_policy.iloc[0]["total_cost"] == 0.0


def test_net_unit_value_mode_uses_user_supplied_net_margin():
    evaluation = tm.evaluate_forest_economics(
        [_example_trajectory()],
        economic_mode="net_unit_value",
        discount_rate=0.0,
        economic_parameters={"net_value_per_dry_t": 50.0},
    )
    assert evaluation.economic_metric == "discounted_net_margin"
    assert evaluation.value_by_policy[("stand_1", "policy_1")] == pytest.approx(
        15_000.0
    )


def test_detailed_cash_flow_builds_true_npv_components():
    evaluation = tm.evaluate_forest_economics(
        [_example_trajectory()],
        economic_mode="detailed_cash_flow",
        discount_rate=0.0,
        economic_parameters={
            "revenue_per_dry_t": 100.0,
            "variable_cost_per_dry_t": 10.0,
            "transport_cost_per_dry_t": 5.0,
            "thinning_cost_per_dry_t": 2.0,
            "final_harvest_cost_per_dry_t": 3.0,
            "thinning_cost_per_ha": 50.0,
            "final_harvest_cost_per_ha": 100.0,
            "replanting_cost_per_ha": 500.0,
            "annual_management_cost_per_ha": 20.0,
        },
    )
    summary = evaluation.summary_by_policy.iloc[0]
    assert evaluation.economic_metric == "net_present_value"
    assert summary["gross_revenue"] == pytest.approx(30_000.0)
    assert summary["total_cost"] == pytest.approx(12_200.0)
    assert summary["economic_value"] == pytest.approx(17_800.0)


def test_delayed_replanting_is_discounted_at_the_delayed_period():
    evaluation = tm.evaluate_forest_economics(
        [_example_trajectory()],
        economic_mode="detailed_cash_flow",
        discount_rate=0.10,
        economic_parameters={
            "revenue_per_dry_t": 0.0,
            "replanting_cost_per_ha": 100.0,
            "replanting_delay_periods": 1,
        },
    )
    replanting = evaluation.cash_flow_table.loc[
        evaluation.cash_flow_table["economic_event"].eq("replanting")
    ]
    assert len(replanting) == 1
    assert replanting.iloc[0]["period"] == 3
    assert replanting.iloc[0]["discounted_economic_value"] == pytest.approx(
        -1000.0 / (1.10**3)
    )


def test_unknown_economic_parameter_is_rejected():
    with pytest.raises(ValueError, match="Unknown economic parameter"):
        tm.evaluate_forest_economics(
            [_example_trajectory()],
            economic_parameters={"unknown_cost": 1.0},
        )


def test_terminal_value_is_discounted_and_added_to_npv():
    trajectory = _example_trajectory().copy()
    trajectory["standing_dry_wood_t_after_operation"] = [180.0, 120.0]
    evaluation = tm.evaluate_forest_economics(
        [trajectory],
        economic_mode="detailed_cash_flow",
        discount_rate=0.10,
        economic_parameters={
            "revenue_per_dry_t": 0.0,
            "terminal_value_per_dry_t": 25.0,
        },
    )
    summary = evaluation.summary_by_policy.iloc[0]
    expected_terminal = 120.0 * 25.0
    assert summary["terminal_value"] == pytest.approx(expected_terminal)
    assert summary["discounted_terminal_value"] == pytest.approx(
        expected_terminal / (1.10**2)
    )
    assert summary["discounted_total_income"] == pytest.approx(
        summary["discounted_terminal_value"]
    )
    assert summary["economic_value"] == pytest.approx(
        summary["discounted_terminal_value"]
    )

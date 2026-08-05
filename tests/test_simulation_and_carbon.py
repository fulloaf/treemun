from pathlib import Path

import pytest

import treemun_sim as tm

ROOT = Path(__file__).resolve().parents[1]
STANDS = ROOT / "examples" / "forest_stands.csv"


@pytest.fixture(scope="module")
def full_simulation():
    return tm.simulate_forest(
        stands_file=STANDS,
        horizon=30,
        include_carbon=True,
        return_carbon_for_optimization=True,
    )


def test_example_generates_expected_number_of_alternatives(full_simulation):
    forest, summary, ending, harvest, carbon = full_simulation
    assert len(forest) == 780
    assert len(summary) == 780
    assert len(ending) == 780
    assert harvest
    assert len(carbon) == 780 * 30


def test_only_supported_operations_are_emitted(full_simulation):
    forest = full_simulation[0]
    operations = set().union(*(set(frame["operation"]) for frame in forest))
    assert operations <= {"none", "thinning", "final_harvest"}
    assert "pruning" not in operations


def test_final_harvest_leaves_zero_post_operation_stock(full_simulation):
    forest = full_simulation[0]
    final_harvest_rows = []
    for frame in forest:
        final_harvest_rows.append(frame.loc[frame["operation"].eq("final_harvest")])
    combined = __import__("pandas").concat(final_harvest_rows, ignore_index=True)
    assert not combined.empty
    assert (combined["standing_dry_wood_t_after_operation"] == 0.0).all()
    assert (
        combined["harvested_dry_wood_t"]
        == combined["standing_dry_wood_t_before_operation"]
    ).all()


def test_thinning_transitions_from_pre_to_post_curve(full_simulation):
    forest = full_simulation[0]
    thinning_rows = __import__("pandas").concat(
        [frame.loc[frame["operation"].eq("thinning")] for frame in forest],
        ignore_index=True,
    )
    assert not thinning_rows.empty
    assert (
        thinning_rows["growth_curve_before_operation"]
        == "pre_thinning_1250_700"
    ).all()
    assert (
        thinning_rows["growth_curve_after_operation"]
        == "post_thinning_700_300"
    ).all()


def test_carbon_is_directly_computed_from_dry_wood(full_simulation):
    forest = full_simulation[0]
    row = forest[0].iloc[0]
    expected = (
        row["standing_dry_wood_t_after_operation"]
        * row["dry_wood_carbon_fraction"]
    )
    assert row["standing_wood_carbon_tC_after_operation"] == pytest.approx(
        expected, abs=1e-6
    )
    assert row["carbon_stock_time_tC_year"] == pytest.approx(expected, abs=1e-6)


def test_random_generation_is_reproducible():
    first = tm.simulate_forest(number_of_stands=6, horizon=30, random_seed=123)
    second = tm.simulate_forest(number_of_stands=6, horizon=30, random_seed=123)
    first_summary = first[1]
    second_summary = second[1]
    assert first_summary == second_summary


def test_thinning_never_leaves_zero_residual_stock(full_simulation):
    forest = full_simulation[0]
    thinning_rows = __import__("pandas").concat(
        [frame.loc[frame["operation"].eq("thinning")] for frame in forest],
        ignore_index=True,
    )
    assert not thinning_rows.empty
    assert (thinning_rows["standing_dry_wood_t_after_operation"] > 0.0).all()


def test_fixed_fraction_fallback_is_used_for_implausibly_low_curve_residuals(
    full_simulation,
):
    forest = full_simulation[0]
    thinning_rows = __import__("pandas").concat(
        [frame.loc[frame["operation"].eq("thinning")] for frame in forest],
        ignore_index=True,
    )
    fallback = thinning_rows.loc[thinning_rows["thinning_fallback_triggered"]]
    assert not fallback.empty
    assert fallback["thinning_calculation_method"].eq(
        "fixed_fraction_fallback"
    ).all()
    assert fallback["candidate_curve_residual_fraction"].le(
        tm.DEFAULT_MINIMUM_CURVE_RESIDUAL_FRACTION
    ).all()
    assert fallback["applied_thinning_fraction"].eq(
        tm.DEFAULT_FALLBACK_THINNING_FRACTION
    ).all()
    expected_remaining = (
        1.0 - tm.DEFAULT_FALLBACK_THINNING_FRACTION
    ) * fallback["standing_dry_wood_t_before_operation"]
    assert fallback["standing_dry_wood_t_after_operation"].to_numpy() == pytest.approx(
        expected_remaining.to_numpy(), abs=1e-3
    )


def test_curve_difference_is_retained_when_residual_is_plausible(full_simulation):
    forest = full_simulation[0]
    thinning_rows = __import__("pandas").concat(
        [frame.loc[frame["operation"].eq("thinning")] for frame in forest],
        ignore_index=True,
    )
    curve_difference = thinning_rows.loc[
        thinning_rows["thinning_calculation_method"].eq("curve_difference")
    ]
    assert not curve_difference.empty
    assert curve_difference["candidate_curve_residual_fraction"].gt(
        tm.DEFAULT_MINIMUM_CURVE_RESIDUAL_FRACTION
    ).all()
    assert curve_difference["standing_dry_wood_t_after_operation"].to_numpy() == pytest.approx(
        curve_difference["candidate_post_thinning_dry_wood_t"].to_numpy(),
        abs=1e-3,
    )


def test_fallback_trajectory_preserves_continuity_with_post_curve_increments(
    full_simulation,
):
    forest = full_simulation[0]
    for trajectory in forest:
        fallback_indices = trajectory.index[
            trajectory["thinning_fallback_triggered"]
        ].tolist()
        if not fallback_indices:
            continue
        thinning_index = fallback_indices[0]
        if thinning_index + 1 >= len(trajectory):
            continue
        next_row = trajectory.iloc[thinning_index + 1]
        if next_row["operation"] == "final_harvest":
            continue
        thinning_row = trajectory.iloc[thinning_index]
        expected_next_stock = (
            next_row["unadjusted_curve_dry_wood_t_before_operation"]
            + thinning_row["post_thinning_continuity_adjustment_t"]
        )
        assert next_row["post_thinning_continuity_adjustment_t"] == pytest.approx(
            thinning_row["post_thinning_continuity_adjustment_t"], abs=1e-3
        )
        assert next_row["standing_dry_wood_t_before_operation"] == pytest.approx(
            expected_next_stock, abs=1e-3
        )
        assert next_row["standing_dry_wood_t_before_operation"] > thinning_row[
            "standing_dry_wood_t_after_operation"
        ]
        return
    pytest.fail("No fallback thinning trajectory with a following growth period was found.")


def test_thinning_transition_parameters_are_validated():
    with pytest.raises(ValueError, match="fallback_thinning_fraction"):
        tm.simulate_forest(number_of_stands=2, fallback_thinning_fraction=1.0)
    with pytest.raises(ValueError, match="minimum_curve_residual_fraction"):
        tm.simulate_forest(number_of_stands=2, minimum_curve_residual_fraction=1.0)


def test_all_pinus_trajectories_start_from_pre_thinning_equations(full_simulation):
    forest = full_simulation[0]
    first_rows = __import__("pandas").concat(
        [frame.iloc[[0]] for frame in forest],
        ignore_index=True,
    )
    pinus_first_rows = first_rows.loc[first_rows["species"].eq(tm.PINUS)]
    assert not pinus_first_rows.empty
    assert pinus_first_rows["growth_curve_before_operation"].str.startswith(
        "pre_thinning"
    ).all()
    assert not pinus_first_rows["growth_curve_before_operation"].str.startswith(
        "post_thinning"
    ).any()


def test_initial_stock_is_policy_invariant_for_every_stand(full_simulation):
    forest = full_simulation[0]
    first_rows = __import__("pandas").concat(
        [frame.iloc[[0]] for frame in forest],
        ignore_index=True,
    )
    distinct_initial_stocks = first_rows.groupby("stand_id")[
        "standing_dry_wood_t_before_operation"
    ].nunique()
    assert distinct_initial_stocks.eq(1).all()


def test_overdue_pinus_thinning_forces_period_one_rotation_reset(full_simulation):
    forest, summary, *_ = full_simulation
    summary_frame = __import__("pandas").DataFrame(summary)
    overdue = summary_frame.loc[
        summary_frame["species"].eq(tm.PINUS)
        & summary_frame["thinning_age"].notna()
        & summary_frame["initial_age"].gt(summary_frame["thinning_age"])
    ]
    assert not overdue.empty

    example = overdue.iloc[0]
    trajectory = next(
        frame
        for frame in forest
        if frame.iloc[0]["stand_id"] == example["stand_id"]
        and frame.iloc[0]["policy"] == example["policy"]
    )
    first = trajectory.iloc[0]
    second = trajectory.iloc[1]

    assert first["operation"] == "final_harvest"
    assert first["final_harvest_reason"] == "overdue_thinning_rotation_reset"
    assert bool(first["initial_rotation_reset_triggered"])
    assert first["growth_curve_before_operation"].startswith("pre_thinning")
    assert first["harvested_dry_wood_t"] == pytest.approx(
        first["standing_dry_wood_t_before_operation"], abs=1e-3
    )
    assert first["standing_dry_wood_t_after_operation"] == 0.0

    assert second["stand_age"] == 1
    assert second["growth_curve_before_operation"].startswith("pre_thinning")
    assert second["operation"] == "none"
    assert not bool(second["initial_rotation_reset_triggered"])


def test_pinus_at_thinning_age_thins_in_period_one_without_rotation_reset(
    full_simulation,
):
    forest, summary, *_ = full_simulation
    summary_frame = __import__("pandas").DataFrame(summary)
    due = summary_frame.loc[
        summary_frame["species"].eq(tm.PINUS)
        & summary_frame["thinning_age"].notna()
        & summary_frame["initial_age"].eq(summary_frame["thinning_age"])
    ]
    assert not due.empty

    example = due.iloc[0]
    trajectory = next(
        frame
        for frame in forest
        if frame.iloc[0]["stand_id"] == example["stand_id"]
        and frame.iloc[0]["policy"] == example["policy"]
    )
    first = trajectory.iloc[0]
    assert first["operation"] == "thinning"
    assert first["growth_curve_before_operation"].startswith("pre_thinning")
    assert first["growth_curve_after_operation"].startswith("post_thinning")
    assert not bool(first["initial_rotation_reset_triggered"])


def test_initial_post_thinning_pinus_state_is_rejected(tmp_path):
    stands = tm.load_stand_table(STANDS)
    lookup = tm.load_lookup_table()
    pine_index = stands.index[stands["species"].eq(tm.PINUS)][0]
    initial_equation = lookup.loc[
        lookup["equation_id"].eq(
            int(
                lookup.loc[
                    lookup["species"].eq(tm.PINUS)
                    & lookup["zone"].eq(int(stands.loc[pine_index, "zone"]))
                    & lookup["site_index"].eq(
                        int(stands.loc[pine_index, "site_index"])
                    )
                    & lookup["management_regime"].eq(
                        stands.loc[pine_index, "management_regime"]
                    )
                    & lookup["growth_curve"].eq(
                        stands.loc[pine_index, "growth_curve"]
                    )
                    & lookup["initial_density_trees_ha"].eq(
                        int(stands.loc[pine_index, "initial_density_trees_ha"])
                    ),
                    "equation_id",
                ].iloc[0]
            )
        )
    ].iloc[0]
    post_equation = lookup.loc[
        lookup["equation_id"].eq(int(initial_equation["next_equation_id"]))
    ].iloc[0]

    stands.loc[pine_index, "growth_curve"] = post_equation["growth_curve"]
    stands.loc[pine_index, "initial_density_trees_ha"] = int(
        post_equation["initial_density_trees_ha"]
    )
    stands_file = tmp_path / "post_thinning_initial_state.csv"
    stands.to_csv(stands_file, index=False)

    with pytest.raises(ValueError, match="must start from a pre-thinning"):
        tm.simulate_forest(stands_file=stands_file, horizon=30)


def test_initial_pinus_equation_without_next_is_rejected(tmp_path):
    stands = tm.load_stand_table(STANDS)
    lookup = tm.load_lookup_table()
    pine = stands.loc[stands["species"].eq(tm.PINUS)].iloc[0]
    mask = (
        lookup["species"].eq(pine["species"])
        & lookup["zone"].eq(int(pine["zone"]))
        & lookup["site_index"].eq(int(pine["site_index"]))
        & lookup["management_regime"].eq(pine["management_regime"])
        & lookup["growth_curve"].eq(pine["growth_curve"])
        & lookup["initial_density_trees_ha"].eq(
            int(pine["initial_density_trees_ha"])
        )
    )
    lookup.loc[mask, "next_equation_id"] = __import__("numpy").nan
    lookup_file = tmp_path / "lookup_without_next.csv"
    lookup.to_csv(lookup_file, index=False)

    with pytest.raises(ValueError, match="without next_equation_id"):
        tm.simulate_forest(
            stands_file=STANDS,
            lookup_table_file=lookup_file,
            horizon=30,
        )

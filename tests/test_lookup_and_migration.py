from pathlib import Path

import pandas as pd
import pytest

import treemun_sim as tm
from treemun_sim.compatibility import migrate_stand_table


def test_lookup_uses_only_canonical_growth_curve_names():
    lookup = tm.load_lookup_table()
    assert set(lookup["growth_curve"]) == {
        "unthinned",
        "pre_thinning_1250_700",
        "post_thinning_700_300",
    }
    joined = " ".join(lookup["growth_curve"].astype(str))
    assert "pruning" not in joined
    assert "post_thinning_1250_700" not in set(lookup["growth_curve"])


def test_pre_thinning_equations_link_to_post_thinning_equations():
    lookup = tm.load_lookup_table()
    by_id = lookup.set_index("equation_id")
    linked = lookup.loc[lookup["next_equation_id"].notna()]
    assert not linked.empty
    for row in linked.itertuples(index=False):
        assert row.growth_curve == "pre_thinning_1250_700"
        assert by_id.loc[int(row.next_equation_id), "growth_curve"] == "post_thinning_700_300"


def test_early_2_0_curve_labels_are_migrated():
    frame = pd.DataFrame(
        {
            "stand_id": ["a", "b"],
            "area_ha": [1.0, 1.0],
            "species": ["Pinus", "Pinus"],
            "initial_age": [5, 12],
            "zone": [6, 6],
            "site_index": [32, 32],
            "management_regime": ["Intensivo", "Intensivo"],
            "growth_curve": [
                "post_thinning_1250_700",
                "post_pruning_thinning_700_300",
            ],
            "initial_density_trees_ha": [1250, 1250],
        }
    )
    with pytest.warns(DeprecationWarning):
        migrated = migrate_stand_table(frame)
    assert migrated["growth_curve"].tolist() == [
        "pre_thinning_1250_700",
        "post_thinning_700_300",
    ]


def test_v1_spanish_stand_file_is_converted(tmp_path: Path):
    source = tmp_path / "v1.csv"
    destination = tmp_path / "v2.csv"
    pd.DataFrame(
        {
            "id_rodal": ["stand1"],
            "hectareas": [10.0],
            "especie": ["Pinus"],
            "edad_inicial": [5],
            "zona": [6],
            "site_index": [32],
            "manejo": ["Intensivo"],
            "condicion": ["PostRaleo1250-700"],
            "densidad_inicial": [1250],
        }
    ).to_csv(source, index=False)
    with pytest.warns(DeprecationWarning):
        tm.convert_v1_stand_file(source, destination)
    converted = pd.read_csv(destination)
    assert converted.loc[0, "growth_curve"] == "pre_thinning_1250_700"
    assert converted.loc[0, "species"] == "Pinus radiata"
    assert converted.loc[0, "management_regime"] == "intensive_1"


def test_unlinked_pinus_equations_are_not_labelled_pre_thinning():
    lookup = tm.load_lookup_table()
    unlinked_pinus = lookup.loc[
        lookup["species"].eq("Pinus radiata")
        & lookup["next_equation_id"].isna()
        & ~lookup["growth_curve"].eq("post_thinning_700_300")
    ]
    assert not unlinked_pinus.empty
    assert unlinked_pinus["growth_curve"].eq("unthinned").all()

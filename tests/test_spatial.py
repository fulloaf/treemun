from pathlib import Path

import treemun_sim as tm

ROOT = Path(__file__).resolve().parents[1]
GEOMETRY = ROOT / "examples" / "treemun_landscape.gpkg"


def test_example_landscape_has_expected_adjacency_edges():
    edges = tm.build_adjacency_edges(GEOMETRY)
    assert len(edges) == 215
    assert set(edges.columns) == {
        "stand_id_a",
        "stand_id_b",
        "shared_boundary_length",
    }
    assert (edges["shared_boundary_length"] > 0).all()

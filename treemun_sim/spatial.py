"""GeoPackage export utilities for Treemün trajectories and solutions."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd


def _require_geopandas():
    try:
        import geopandas as gpd
    except ImportError as exc:
        raise ImportError(
            "Spatial functions require GeoPandas. Install with "
            "`pip install treemun-sim[spatial]`."
        ) from exc
    return gpd


def _load_geometries(
    geometry_file: str | Path,
    *,
    stand_id_column: str = "stand_id",
):
    gpd = _require_geopandas()
    geometries = gpd.read_file(geometry_file)
    if stand_id_column not in geometries.columns:
        if stand_id_column == "stand_id" and "id_rodal" in geometries.columns:
            geometries = geometries.rename(columns={"id_rodal": "stand_id"})
        else:
            raise ValueError(
                f"Geometry file does not contain {stand_id_column!r}. "
                f"Available columns: {list(geometries.columns)}"
            )
    geometries[stand_id_column] = geometries[stand_id_column].astype(str)
    if geometries[stand_id_column].duplicated().any():
        raise ValueError("Geometry stand identifiers must be unique.")
    if geometries.geometry.isna().any() or geometries.geometry.is_empty.any():
        raise ValueError("Geometry file contains empty geometries.")
    return geometries


def forest_to_long_table(forest: Sequence[pd.DataFrame]) -> pd.DataFrame:
    """Concatenate simulated trajectories into a canonical long table."""
    if not forest:
        raise ValueError("forest cannot be empty.")
    return pd.concat([trajectory.copy() for trajectory in forest], ignore_index=True)


def export_simulation_to_geopackage(
    *,
    forest: Sequence[pd.DataFrame],
    geometry_file: str | Path,
    output_file: str | Path,
    stand_id_column: str = "stand_id",
    layer: str = "simulation",
):
    """Export all stand-policy-period trajectories as a long GeoPackage layer."""
    gpd = _require_geopandas()
    geometries = _load_geometries(
        geometry_file, stand_id_column=stand_id_column
    )[[stand_id_column, "geometry"]]
    simulation = forest_to_long_table(forest)
    simulation["stand_id"] = simulation["stand_id"].astype(str)
    missing = set(simulation["stand_id"]) - set(geometries[stand_id_column])
    if missing:
        raise ValueError(f"Missing geometries for stand IDs: {sorted(missing)}")

    merged = simulation.merge(
        geometries,
        left_on="stand_id",
        right_on=stand_id_column,
        how="left",
        validate="many_to_one",
    )
    if stand_id_column != "stand_id":
        merged = merged.drop(columns=[stand_id_column])
    output = gpd.GeoDataFrame(merged, geometry="geometry", crs=geometries.crs)
    destination = Path(output_file)
    destination.parent.mkdir(parents=True, exist_ok=True)
    output.to_file(destination, layer=layer, driver="GPKG")
    return output


def export_optimal_solution_to_geopackage(
    *,
    forest: Sequence[pd.DataFrame],
    solution: Mapping[str, object],
    geometry_file: str | Path,
    output_file: str | Path,
    stand_id_column: str = "stand_id",
    layer: str = "optimal_solution",
):
    """Export annual trajectories for only the selected stand policies."""
    selected = solution.get("selected_policies")
    if selected is None:
        raise ValueError("solution does not contain selected_policies.")
    selected_frame = pd.DataFrame(selected).copy()
    required = {"stand_id", "policy"}
    missing_columns = required - set(selected_frame.columns)
    if missing_columns:
        raise ValueError(
            f"selected_policies is missing columns: {sorted(missing_columns)}"
        )

    long_table = forest_to_long_table(forest)
    selected_long = long_table.merge(
        selected_frame[["stand_id", "policy"]].drop_duplicates(),
        on=["stand_id", "policy"],
        how="inner",
        validate="many_to_one",
    )
    return export_simulation_to_geopackage(
        forest=[selected_long],
        geometry_file=geometry_file,
        output_file=output_file,
        stand_id_column=stand_id_column,
        layer=layer,
    )

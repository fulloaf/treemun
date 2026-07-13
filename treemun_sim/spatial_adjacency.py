# treemun_sim/spatial_adjacency.py
"""
Spatial adjacency utilities for treemun-sim.

This module builds adjacency edges from stand geometries and creates the
final-harvest indicator used by adjacency-aware harvest-scheduling constraints.

Python 3.9 compatible version.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple, Union

import pandas as pd


def _make_valid_geometry_series(geoseries):
    """Return a valid geometry series, compatible with older GeoPandas/Shapely."""
    try:
        return geoseries.make_valid()
    except Exception:
        return geoseries.buffer(0)


def build_adjacency_edges(
    shapefile_path: str,
    id_col: str = "id_rodal",
    min_shared_boundary: float = 1.0,
    export_csv_path: Optional[str] = None,
    return_dataframe: bool = False,
):
    """
    Build stand-adjacency edges from a polygon shapefile.

    Two stands are considered adjacent if their boundaries share a line segment
    whose length is at least ``min_shared_boundary``. This avoids treating
    polygons that only touch at a point as adjacent.

    Parameters
    ----------
    shapefile_path : str
        Path to the stand polygon shapefile.
    id_col : str, default "id_rodal"
        Column containing the stand identifier used by the optimization model.
    min_shared_boundary : float, default 1.0
        Minimum shared-boundary length, in CRS units, required to create an edge.
        For projected CRSs such as EPSG:32718, units are meters.
    export_csv_path : str or None, default None
        If provided, writes the edge table to this CSV path.
    return_dataframe : bool, default False
        If True, return the full edge DataFrame. If False, return only a list of
        ``(stand_id_1, stand_id_2)`` tuples.

    Returns
    -------
    list[tuple[str, str]] or pandas.DataFrame
        Adjacency list or edge table with shared-boundary lengths.
    """
    import geopandas as gpd

    gdf = gpd.read_file(shapefile_path)

    if id_col not in gdf.columns:
        raise ValueError(f"Column '{id_col}' was not found in {shapefile_path}.")

    gdf = gdf[[id_col, "geometry"]].copy()
    gdf[id_col] = gdf[id_col].astype(str)
    gdf["geometry"] = _make_valid_geometry_series(gdf.geometry)

    sindex = gdf.sindex
    rows = []

    for pos_i, geom_i in enumerate(gdf.geometry):
        stand_i = gdf.iloc[pos_i][id_col]

        candidate_positions = sindex.query(geom_i, predicate="intersects")

        for pos_j in candidate_positions:
            if pos_j <= pos_i:
                continue

            geom_j = gdf.geometry.iloc[pos_j]
            stand_j = gdf.iloc[pos_j][id_col]

            shared_boundary = geom_i.boundary.intersection(geom_j.boundary)
            shared_length = float(shared_boundary.length)

            if shared_length >= float(min_shared_boundary):
                rows.append(
                    {
                        "stand_id_1": stand_i,
                        "stand_id_2": stand_j,
                        "shared_boundary_m": shared_length,
                    }
                )

    edges_df = pd.DataFrame(rows)

    if not edges_df.empty:
        edges_df = edges_df.sort_values(["stand_id_1", "stand_id_2"]).reset_index(drop=True)

    if export_csv_path is not None:
        edges_df.to_csv(export_csv_path, index=False)

    if return_dataframe:
        return edges_df

    if edges_df.empty:
        return []

    return list(edges_df[["stand_id_1", "stand_id_2"]].itertuples(index=False, name=None))


def _first_existing_column(df: pd.DataFrame, candidates: Iterable[str], label: str) -> str:
    """Return the first column from candidates present in df, or raise."""
    for col in candidates:
        if col in df.columns:
            return col
    raise ValueError(f"Could not find a {label} column. Tried: {list(candidates)}")


def _species_group(value: object) -> str:
    """Normalize species names into 'pine' or 'eucalyptus'."""
    text = str(value).strip().lower()
    if "pinus" in text or "pino" in text:
        return "pine"
    if "euca" in text:
        return "eucalyptus"
    raise ValueError(f"Unrecognized species value: {value!r}")


def build_final_harvest_indicator(
    stands: Union[str, pd.DataFrame],
    policies_pino: List[Tuple[int, int]],
    policies_eucalyptus: List[Tuple[int]],
    horizon: int,
    id_col: str = "id_rodal",
    species_col: Optional[str] = None,
    age_col: Optional[str] = None,
    pine_output_species: str = "Pinus",
    eucalyptus_output_species: str = "Eucapyltus",
) -> Dict[Tuple[int, str, str, str], int]:
    """
    Build the final-harvest indicator used by adjacency constraints.

    The returned dictionary has keys compatible with treemun-sim optimization
    dictionaries:

        (period, species_key, policy_name, stand_id) -> 1

    Only final-harvest events are flagged. Thinning events are ignored because
    they do not necessarily create a spatial opening equivalent to final harvest.
    """
    if isinstance(stands, str):
        if stands.lower().endswith(".txt"):
            df = pd.read_csv(stands, sep=None, engine="python")
        else:
            df = pd.read_csv(stands)
    else:
        df = stands.copy()

    if id_col not in df.columns:
        raise ValueError(f"Column '{id_col}' was not found in the stands table.")

    if species_col is None:
        species_col = _first_existing_column(
            df,
            candidates=["especie", "Especie", "species", "Species"],
            label="species",
        )

    if age_col is None:
        age_col = _first_existing_column(
            df,
            candidates=["edad_ini", "edad_inicial", "EdadInicial", "initial_age", "age"],
            label="initial-age",
        )

    indicator: Dict[Tuple[int, str, str, str], int] = {}

    for _, row in df.iterrows():
        stand_id = str(row[id_col])
        species_group = _species_group(row[species_col])
        initial_age = int(row[age_col])

        if species_group == "pine":
            policies = [
                (f"policy_pino {idx}", pine_output_species, int(policy[-1]))
                for idx, policy in enumerate(policies_pino, start=1)
            ]
        else:
            policies = [
                (f"policy_eucalyptus {idx}", eucalyptus_output_species, int(policy[0]))
                for idx, policy in enumerate(policies_eucalyptus, start=1)
            ]

        for policy_name, species_key, harvest_age in policies:
            age = initial_age

            for t in range(1, int(horizon) + 1):
                if age >= harvest_age:
                    indicator[(t, species_key, policy_name, stand_id)] = 1
                    # Also store standard eucalyptus spelling for robustness.
                    if species_key == "Eucapyltus":
                        indicator[(t, "Eucalyptus", policy_name, stand_id)] = 1
                    age = 1
                else:
                    age += 1

    return indicator

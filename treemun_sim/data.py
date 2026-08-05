"""Data loading and validation for Treemün."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Final

import pandas as pd

from .compatibility import migrate_lookup_table, migrate_stand_table

LOOKUP_INDEX_COLUMNS: Final[tuple[str, ...]] = (
    "species",
    "zone",
    "site_index",
    "management_regime",
    "growth_curve",
    "initial_density_trees_ha",
)

REQUIRED_LOOKUP_COLUMNS: Final[set[str]] = {
    "equation_id",
    "next_equation_id",
    *LOOKUP_INDEX_COLUMNS,
    "alpha",
    "beta",
    "gamma",
}

REQUIRED_STAND_COLUMNS: Final[set[str]] = {
    "stand_id",
    "area_ha",
    "species",
    "initial_age",
    "zone",
    "site_index",
    "management_regime",
    "growth_curve",
    "initial_density_trees_ha",
}


def _validate_unique_columns(frame: pd.DataFrame, *, label: str) -> None:
    duplicated = frame.columns[frame.columns.duplicated()].tolist()
    if duplicated:
        raise ValueError(f"{label} contains duplicate columns: {duplicated}")


def load_lookup_table(path: str | Path | None = None) -> pd.DataFrame:
    """Load and validate the growth-equation lookup table.

    The returned table retains ordinary columns. Use :func:`lookup_index` when
    an indexed representation is required.
    """
    lookup_path = (
        Path(path)
        if path is not None
        else Path(files("treemun_sim").joinpath("data/lookup_table.csv"))
    )
    if not lookup_path.exists():
        raise FileNotFoundError(f"Lookup table not found: {lookup_path}")

    frame = pd.read_csv(lookup_path, keep_default_na=False)
    _validate_unique_columns(frame, label="lookup table")
    frame = migrate_lookup_table(frame)

    missing = REQUIRED_LOOKUP_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Lookup table is missing columns: {sorted(missing)}")

    numeric_columns = [
        "equation_id",
        "zone",
        "site_index",
        "initial_density_trees_ha",
        "alpha",
        "beta",
        "gamma",
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    frame["next_equation_id"] = pd.to_numeric(
        frame["next_equation_id"], errors="coerce"
    ).astype("Int64")
    frame["equation_id"] = frame["equation_id"].astype(int)
    frame["zone"] = frame["zone"].astype(int)
    frame["site_index"] = frame["site_index"].astype(int)
    frame["initial_density_trees_ha"] = frame[
        "initial_density_trees_ha"
    ].astype(int)

    if frame["equation_id"].duplicated().any():
        duplicates = frame.loc[
            frame["equation_id"].duplicated(keep=False), "equation_id"
        ].tolist()
        raise ValueError(f"Duplicate equation_id values: {duplicates}")

    duplicate_keys = frame.duplicated(list(LOOKUP_INDEX_COLUMNS), keep=False)
    if duplicate_keys.any():
        records = frame.loc[duplicate_keys, list(LOOKUP_INDEX_COLUMNS)].to_dict("records")
        raise ValueError(f"Duplicate lookup combinations: {records}")

    known_ids = set(frame["equation_id"])
    unknown_next = {
        int(value)
        for value in frame["next_equation_id"].dropna()
        if int(value) not in known_ids
    }
    if unknown_next:
        raise ValueError(f"Unknown next_equation_id values: {sorted(unknown_next)}")

    return frame.sort_values("equation_id").reset_index(drop=True)


def lookup_index(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the lookup table indexed by its canonical stand descriptors."""
    return frame.set_index(list(LOOKUP_INDEX_COLUMNS), drop=False)


def load_stand_table(path: str | Path) -> pd.DataFrame:
    """Load, migrate, and validate a stand CSV or tab-delimited text file."""
    stand_path = Path(path)
    if not stand_path.exists():
        raise FileNotFoundError(f"Stand file not found: {stand_path}")

    separator = "\t" if stand_path.suffix.lower() == ".txt" else ","
    frame = pd.read_csv(stand_path, sep=separator)
    _validate_unique_columns(frame, label="stand table")
    frame = migrate_stand_table(frame)

    missing = REQUIRED_STAND_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Stand table is missing columns: {sorted(missing)}")

    if frame["stand_id"].isna().any() or frame["stand_id"].astype(str).str.strip().eq("").any():
        raise ValueError("stand_id cannot be empty.")
    frame["stand_id"] = frame["stand_id"].astype(str)
    if frame["stand_id"].duplicated().any():
        duplicates = frame.loc[
            frame["stand_id"].duplicated(keep=False), "stand_id"
        ].tolist()
        raise ValueError(f"Duplicate stand_id values: {duplicates}")

    integer_columns = [
        "initial_age",
        "zone",
        "site_index",
        "initial_density_trees_ha",
    ]
    for column in integer_columns:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(int)
    frame["area_ha"] = pd.to_numeric(frame["area_ha"], errors="raise")

    if (frame["area_ha"] <= 0).any():
        raise ValueError("All area_ha values must be greater than zero.")
    if (frame["initial_age"] < 1).any():
        raise ValueError("All initial_age values must be at least one year.")

    return frame.reset_index(drop=True)


def validate_stands_against_lookup(
    stands: pd.DataFrame,
    lookup: pd.DataFrame,
) -> None:
    """Validate initial stand equations and mandatory Pinus transitions.

    Every stand must match exactly one lookup row. Pinus stands must start from
    a pre-thinning equation with a valid ``next_equation_id`` that references a
    post-thinning Pinus equation. Post-thinning equations are internal
    simulation states and cannot be supplied as initial stand conditions.
    """
    lookup_by_key = {
        tuple(getattr(row, column) for column in LOOKUP_INDEX_COLUMNS): row
        for row in lookup.itertuples(index=False)
    }
    lookup_by_id = {
        int(row.equation_id): row
        for row in lookup.itertuples(index=False)
    }

    invalid: list[dict[str, object]] = []
    transition_errors: list[str] = []
    for row in stands.itertuples(index=False):
        key = tuple(getattr(row, column) for column in LOOKUP_INDEX_COLUMNS)
        equation = lookup_by_key.get(key)
        if equation is None:
            invalid.append(
                {
                    "stand_id": row.stand_id,
                    **{column: value for column, value in zip(LOOKUP_INDEX_COLUMNS, key)},
                }
            )
            continue

        if str(row.species) != "Pinus radiata":
            continue

        if not str(equation.growth_curve).startswith("pre_thinning"):
            transition_errors.append(
                f"stand {row.stand_id!r} must start from a pre-thinning "
                f"equation, not {equation.growth_curve!r}"
            )
            continue

        next_id = equation.next_equation_id
        if pd.isna(next_id):
            transition_errors.append(
                f"stand {row.stand_id!r} uses Pinus equation "
                f"{equation.equation_id} without next_equation_id"
            )
            continue

        next_equation = lookup_by_id.get(int(next_id))
        if next_equation is None:
            transition_errors.append(
                f"stand {row.stand_id!r} references unknown "
                f"next_equation_id {int(next_id)}"
            )
            continue
        if str(next_equation.species) != "Pinus radiata":
            transition_errors.append(
                f"stand {row.stand_id!r} next_equation_id {int(next_id)} "
                "does not reference Pinus radiata"
            )
        elif not str(next_equation.growth_curve).startswith("post_thinning"):
            transition_errors.append(
                f"stand {row.stand_id!r} next_equation_id {int(next_id)} "
                f"must reference a post-thinning equation, not "
                f"{next_equation.growth_curve!r}"
            )

    if invalid:
        raise ValueError(
            "Stand configurations not found in lookup_table.csv: "
            f"{invalid[:10]}" + (" ..." if len(invalid) > 10 else "")
        )
    if transition_errors:
        raise ValueError(
            "Invalid initial Pinus growth transition: "
            + "; ".join(transition_errors[:10])
            + (" ..." if len(transition_errors) > 10 else "")
        )

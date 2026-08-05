"""Compatibility helpers for migrating Treemün 1.x and early 2.0 inputs."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Mapping

import pandas as pd

LEGACY_STAND_COLUMN_ALIASES: Mapping[str, str] = {
    "id_rodal": "stand_id",
    "hectareas": "area_ha",
    "especie": "species",
    "edad_inicial": "initial_age",
    "zona": "zone",
    "indice_sitio": "site_index",
    "manejo": "management_regime",
    "condicion": "growth_curve",
    "condición": "growth_curve",
    "densidad_inicial": "initial_density_trees_ha",
}

LEGACY_LOOKUP_COLUMN_ALIASES: Mapping[str, str] = {
    "id": "equation_id",
    "next": "next_equation_id",
    "Especie": "species",
    "Zona": "zone",
    "DensidadInicial": "initial_density_trees_ha",
    "SiteIndex": "site_index",
    "Manejo": "management_regime",
    "Condicion": "growth_curve",
    "α": "alpha",
    "β": "beta",
    "γ": "gamma",
}

SPECIES_ALIASES: Mapping[str, str] = {
    "pinus": "Pinus radiata",
    "pino": "Pinus radiata",
    "pinus radiata": "Pinus radiata",
    "eucalyptus": "Eucalyptus globulus",
    "eucapyltus": "Eucalyptus globulus",
    "eucalipto": "Eucalyptus globulus",
    "eucalyptus globulus": "Eucalyptus globulus",
}

MANAGEMENT_REGIME_ALIASES: Mapping[str, str] = {
    "": "none",
    "na": "none",
    "nan": "none",
    "none": "none",
    "sin manejo": "none",
    "sinmanejo": "none",
    "intensivo": "intensive_1",
    "intensive": "intensive_1",
    "intensive_1": "intensive_1",
    "intensivo2": "intensive_2",
    "intensive_2": "intensive_2",
    "multipropósito": "multipurpose",
    "multiproposito": "multipurpose",
    "multipurpose": "multipurpose",
    "pulpable": "pulpwood",
    "pulpwood": "pulpwood",
}

# Canonical curve names deliberately describe whether a curve applies before or
# after thinning. Pruning is not represented as a separate operation.
GROWTH_CURVE_ALIASES: Mapping[str, str] = {
    "unthinned": "unthinned",
    "sinmanejo": "unthinned",
    "sin manejo": "unthinned",
    "postraleo1250-700": "pre_thinning_1250_700",
    "post_thinning_1250_700": "pre_thinning_1250_700",
    "pre_thinning_1250_700": "pre_thinning_1250_700",
    "postpodayraleo700-300": "post_thinning_700_300",
    "post_pruning_thinning_700_300": "post_thinning_700_300",
    "post_thinning_700_300": "post_thinning_700_300",
}


def _warn_legacy(message: str) -> None:
    warnings.warn(message, DeprecationWarning, stacklevel=3)


def rename_legacy_columns(
    frame: pd.DataFrame,
    aliases: Mapping[str, str],
    *,
    source_name: str,
) -> pd.DataFrame:
    """Return a copy with legacy columns renamed to the canonical schema."""
    renamed = frame.copy()
    replacements: dict[str, str] = {}
    for old_name, new_name in aliases.items():
        if old_name not in renamed.columns:
            continue
        if new_name in renamed.columns and old_name != new_name:
            raise ValueError(
                f"{source_name} contains both legacy column {old_name!r} and "
                f"canonical column {new_name!r}. Remove one of them."
            )
        replacements[old_name] = new_name
    if replacements:
        _warn_legacy(
            f"{source_name} uses deprecated Treemün 1.x column names. "
            "They were converted to the Treemün 2.0 English schema."
        )
        renamed = renamed.rename(columns=replacements)
    return renamed


def normalize_species(value: object) -> str:
    key = str(value).strip().lower()
    try:
        return SPECIES_ALIASES[key]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported species {value!r}. Use 'Pinus radiata' or "
            "'Eucalyptus globulus'."
        ) from exc


def normalize_management_regime(value: object) -> str:
    if pd.isna(value):
        return "none"
    key = str(value).strip().lower()
    try:
        return MANAGEMENT_REGIME_ALIASES[key]
    except KeyError as exc:
        raise ValueError(f"Unsupported management_regime {value!r}.") from exc


def normalize_growth_curve(value: object) -> str:
    key = str(value).strip().lower()
    try:
        canonical = GROWTH_CURVE_ALIASES[key]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported growth_curve {value!r}. Expected one of: "
            "unthinned, pre_thinning_1250_700, post_thinning_700_300."
        ) from exc
    if key in {"post_thinning_1250_700", "post_pruning_thinning_700_300"}:
        _warn_legacy(
            f"Growth-curve label {value!r} is deprecated and was converted to "
            f"{canonical!r}."
        )
    return canonical


def migrate_stand_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert a stand table to the canonical Treemün 2.0 schema."""
    migrated = rename_legacy_columns(
        frame, LEGACY_STAND_COLUMN_ALIASES, source_name="stand table"
    )
    if "species" in migrated:
        migrated["species"] = migrated["species"].map(normalize_species)
    if "management_regime" in migrated:
        migrated["management_regime"] = migrated["management_regime"].map(
            normalize_management_regime
        )
    if "growth_curve" in migrated:
        migrated["growth_curve"] = migrated["growth_curve"].map(
            normalize_growth_curve
        )
    return migrated


def migrate_lookup_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert a lookup table to the canonical Treemün 2.0 schema."""
    migrated = rename_legacy_columns(
        frame, LEGACY_LOOKUP_COLUMN_ALIASES, source_name="lookup table"
    )
    if "species" in migrated:
        migrated["species"] = migrated["species"].map(normalize_species)
    if "management_regime" in migrated:
        migrated["management_regime"] = migrated["management_regime"].map(
            normalize_management_regime
        )
    if "growth_curve" in migrated:
        migrated["growth_curve"] = migrated["growth_curve"].map(
            normalize_growth_curve
        )
    return migrated


def convert_v1_stand_file(input_path: str | Path, output_path: str | Path) -> Path:
    """Convert a Treemün 1.x stand CSV to the canonical 2.0 schema."""
    source = Path(input_path)
    destination = Path(output_path)
    frame = pd.read_csv(source)
    migrate_stand_table(frame).to_csv(destination, index=False)
    return destination

"""Standing-wood carbon accounting for Treemün trajectories.

The module converts oven-dry wood mass directly to carbon mass. It does not
apply wood density because the growth equations already return dry-wood mass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import pandas as pd

from .simulation import EUCALYPTUS, PINUS

CO2E_FACTOR = 44.0 / 12.0


@dataclass(frozen=True)
class SpeciesCarbonParameter:
    """Dry-wood carbon fraction for one species."""

    carbon_fraction: float

    def __post_init__(self) -> None:
        if not 0.0 < float(self.carbon_fraction) <= 1.0:
            raise ValueError("carbon_fraction must be in (0, 1].")


DEFAULT_SPECIES_CARBON_PARAMETERS: Mapping[str, SpeciesCarbonParameter] = {
    PINUS: SpeciesCarbonParameter(carbon_fraction=0.48),
    EUCALYPTUS: SpeciesCarbonParameter(carbon_fraction=0.51),
}


class StandingWoodCarbonAccounting:
    """Add standing-wood carbon stocks and stock-time to trajectories.

    Notes
    -----
    This is a standing-wood-only accounting layer. It excludes roots, foliage,
    soil, dead wood, harvested-wood products, decay, substitution effects, and
    operational emissions.
    """

    def __init__(
        self,
        species_parameters: Mapping[str, SpeciesCarbonParameter | float] | None = None,
        *,
        period_years: float = 1.0,
    ) -> None:
        if period_years <= 0:
            raise ValueError("period_years must be greater than zero.")
        supplied = species_parameters or DEFAULT_SPECIES_CARBON_PARAMETERS
        self.species_parameters: dict[str, SpeciesCarbonParameter] = {}
        for species, parameter in supplied.items():
            self.species_parameters[species] = (
                parameter
                if isinstance(parameter, SpeciesCarbonParameter)
                else SpeciesCarbonParameter(float(parameter))
            )
        self.period_years = float(period_years)

    def carbon_fraction(self, species: str) -> float:
        try:
            return self.species_parameters[species].carbon_fraction
        except KeyError as exc:
            raise ValueError(f"No carbon parameter configured for {species!r}.") from exc

    def add_to_trajectory(self, trajectory: pd.DataFrame) -> pd.DataFrame:
        required = {
            "species",
            "standing_dry_wood_t_before_operation",
            "harvested_dry_wood_t",
            "standing_dry_wood_t_after_operation",
        }
        missing = required - set(trajectory.columns)
        if missing:
            raise ValueError(f"Trajectory is missing carbon input columns: {sorted(missing)}")

        result = trajectory.copy()
        fractions = result["species"].map(self.carbon_fraction)
        result["dry_wood_carbon_fraction"] = fractions
        result["standing_wood_carbon_tC_before_operation"] = (
            result["standing_dry_wood_t_before_operation"] * fractions
        )
        result["harvested_wood_carbon_tC"] = (
            result["harvested_dry_wood_t"] * fractions
        )
        result["standing_wood_carbon_tC_after_operation"] = (
            result["standing_dry_wood_t_after_operation"] * fractions
        )
        result["standing_wood_co2e_t_after_operation"] = (
            result["standing_wood_carbon_tC_after_operation"] * CO2E_FACTOR
        )
        result["carbon_stock_time_tC_year"] = (
            result["standing_wood_carbon_tC_after_operation"] * self.period_years
        )
        result["cumulative_carbon_stock_time_tC_year"] = result[
            "carbon_stock_time_tC_year"
        ].cumsum()

        carbon_columns = [
            "standing_wood_carbon_tC_before_operation",
            "harvested_wood_carbon_tC",
            "standing_wood_carbon_tC_after_operation",
            "standing_wood_co2e_t_after_operation",
            "carbon_stock_time_tC_year",
            "cumulative_carbon_stock_time_tC_year",
        ]
        result[carbon_columns] = result[carbon_columns].round(6)
        return result

    def add_to_forest(self, forest: Sequence[pd.DataFrame]) -> list[pd.DataFrame]:
        return [self.add_to_trajectory(trajectory) for trajectory in forest]

    def stock_time_coefficients(
        self,
        forest: Sequence[pd.DataFrame],
    ) -> dict[tuple[int, str, str, str], float]:
        """Return annual standing-carbon stock-time coefficients for optimization."""
        coefficients: dict[tuple[int, str, str, str], float] = {}
        for trajectory in forest:
            enriched = (
                trajectory
                if "carbon_stock_time_tC_year" in trajectory.columns
                else self.add_to_trajectory(trajectory)
            )
            for row in enriched.itertuples(index=False):
                coefficients[(row.period, row.species, row.policy, row.stand_id)] = float(
                    row.carbon_stock_time_tC_year
                )
        return coefficients

    def ending_carbon_by_policy(
        self,
        forest: Sequence[pd.DataFrame],
    ) -> dict[tuple[str, str], float]:
        coefficients: dict[tuple[str, str], float] = {}
        for trajectory in forest:
            enriched = (
                trajectory
                if "standing_wood_carbon_tC_after_operation" in trajectory.columns
                else self.add_to_trajectory(trajectory)
            )
            last = enriched.iloc[-1]
            coefficients[(str(last["stand_id"]), str(last["policy"]))] = float(
                last["standing_wood_carbon_tC_after_operation"]
            )
        return coefficients


def add_carbon_accounting(
    forest: Sequence[pd.DataFrame],
    *,
    species_parameters: Mapping[str, SpeciesCarbonParameter | float] | None = None,
    period_years: float = 1.0,
) -> list[pd.DataFrame]:
    """Convenience wrapper for :class:`StandingWoodCarbonAccounting`."""
    return StandingWoodCarbonAccounting(
        species_parameters, period_years=period_years
    ).add_to_forest(forest)

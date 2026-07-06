"""Carbon accounting utilities for treemun-sim.

This module adds a simple, transparent carbon proxy to the list of DataFrames
returned by treemun-sim. It is designed as a post-processing layer: it does not
modify the growth/yield simulator.

Core interpretation
-------------------
For each stand-policy trajectory and period t, treemun-sim provides:

    biomasa_t : simulated total aerial volume before the silvicultural operation
                in period t, in m3.
    bioOPT_t  : volume removed in period t by thinning or final harvest, in m3.

This module therefore computes three carbon quantities:

    CarbonStockPre_t      = alpha_species * biomasa_t
    RemovedCarbon_t       = alpha_species * bioOPT_t
    CarbonStockPost_t     = alpha_species * max(biomasa_t - bioOPT_t, 0)

The net period carbon-stock change is computed from post-operation stocks:

    CarbSeq_t = CarbonStockPost_t - CarbonStockPost_{t-1}

Negative values are valid and expected when thinning/harvest reduces standing
live biomass. These values should be interpreted as reductions in the
above-ground live carbon stock, not as direct atmospheric emissions.

The same quantities are also expressed in CO2 equivalent using 44/12.

Default coefficients
--------------------
The default species-level coefficients are:

    Eucalyptus: rho = 0.567 Mg dry matter m-3, CF = 0.51
    Pinus:      rho = 0.377 Mg dry matter m-3, CF = 0.48

where alpha_species = rho * CF, in Mg C m-3.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

import numpy as np
import pandas as pd


CO2E_FACTOR = 44.0 / 12.0


@dataclass(frozen=True)
class SpeciesCarbonParameter:
    """Volume-to-carbon conversion parameters for one species.

    Parameters
    ----------
    wood_basic_density_Mg_m3:
        Basic wood density in Mg dry matter per cubic meter.
    carbon_fraction:
        Carbon fraction of dry matter.
    """

    wood_basic_density_Mg_m3: float
    carbon_fraction: float

    @property
    def alpha_MgC_m3(self) -> float:
        """Conversion factor from m3 of aerial volume to Mg C."""
        return self.wood_basic_density_Mg_m3 * self.carbon_fraction

    @property
    def alpha_MgCO2e_m3(self) -> float:
        """Conversion factor from m3 of aerial volume to Mg CO2e."""
        return self.alpha_MgC_m3 * CO2E_FACTOR


DEFAULT_SPECIES_CARBON_PARAMETERS: Dict[str, SpeciesCarbonParameter] = {
    # Eucalyptus globulus: single species-level coefficient.
    # rho = 0.567 Mg m-3, CF = 0.51 -> alpha = 0.28917 Mg C m-3.
    "Eucalyptus": SpeciesCarbonParameter(
        wood_basic_density_Mg_m3=0.567,
        carbon_fraction=0.51,
    ),
    # Pinus radiata: single species-level coefficient.
    # rho = 0.377 Mg m-3, CF = 0.48 -> alpha = 0.18096 Mg C m-3.
    "Pinus": SpeciesCarbonParameter(
        wood_basic_density_Mg_m3=0.377,
        carbon_fraction=0.48,
    ),
}


class CarbonSequestrationProxy:
    """Adds carbon-stock and carbon-stock-change columns to treemun outputs.

    The class assumes that each DataFrame in ``bosque`` corresponds to one
    stand-policy trajectory.

    New columns added
    -----------------
    ``CarbonAlpha_MgC_m3``
        Species-specific coefficient alpha = rho * CF.
    ``CarbonAlpha_MgCO2e_m3``
        Species-specific CO2e coefficient alpha * 44/12.
    ``VolumePreOperation_m3``
        Copy of ``biomasa`` interpreted as pre-operation standing volume.
    ``RemovedVolume_m3``
        Copy of ``bioOPT`` interpreted as removed volume.
    ``VolumePostOperation_m3``
        max(``biomasa`` - ``bioOPT``, 0).
    ``CarbonStockPre_MgC`` and ``CarbonStockPre_MgCO2e``
        Carbon stock before the operation in each period.
    ``RemovedCarbon_MgC`` and ``RemovedCarbon_MgCO2e``
        Carbon contained in the removed volume.
    ``CarbonStockPost_MgC`` and ``CarbonStockPost_MgCO2e``
        Standing live carbon stock after the operation.
    ``CarbSeq_MgC`` and ``CarbSeq_MgCO2e``
        Period-to-period net change in post-operation carbon stock.
    ``CarbSeqOPT`` and ``CarbEqvOPT``
        Values of ``CarbSeq_MgC`` and ``CarbSeq_MgCO2e`` only in periods where
        ``bioOPT`` is nonzero. These columns are aligned with the current
        optimization logic based on operational periods.

    Notes
    -----
    * Negative ``CarbSeq`` and ``CarbSeqOPT`` values are allowed.
    * The first period has no previous post-operation stock in the treemun
      output. By default it is assigned 0; set ``first_period_sequestration``
      to ``np.nan`` if you prefer to mark it as undefined.
    """

    def __init__(
        self,
        species_parameters: Optional[Mapping[str, SpeciesCarbonParameter]] = None,
        volume_column: str = "biomasa",
        harvest_column: str = "bioOPT",
        species_column: str = "Especie",
        period_column: str = "periodo",
        policy_column: str = "politica",
        stand_column: str = "id_rodal",
        first_period_sequestration: float = 0.0,
        operation_tolerance: float = 1e-12,
        rounding: Optional[int] = 6,
    ) -> None:
        raw_parameters = species_parameters or DEFAULT_SPECIES_CARBON_PARAMETERS
        self.species_parameters = {
            self.normalize_species_name(species): parameter
            for species, parameter in raw_parameters.items()
        }

        self.volume_column = volume_column
        self.harvest_column = harvest_column
        self.species_column = species_column
        self.period_column = period_column
        self.policy_column = policy_column
        self.stand_column = stand_column
        self.first_period_sequestration = first_period_sequestration
        self.operation_tolerance = operation_tolerance
        self.rounding = rounding

    @staticmethod
    def normalize_species_name(species: object) -> str:
        """Normalizes treemun species labels to ``Pinus`` or ``Eucalyptus``.

        The current treemun output may contain ``Eucapyltus``. This method also
        accepts common variants such as ``Eucalyptus globulus``.
        """
        if pd.isna(species):
            raise ValueError("Species value is missing; cannot assign carbon parameters.")

        value = str(species).strip().lower()

        if value.startswith("pinus") or value in {"pino", "pine", "pinus radiata"}:
            return "Pinus"

        if (
            value.startswith("euca")
            or value.startswith("eucalyptus")
            or value in {"eucalipto", "eucalyptus globulus", "eucapyltus"}
        ):
            return "Eucalyptus"

        raise ValueError(
            f"Unsupported species label '{species}'. Expected Pinus or Eucalyptus."
        )

    def parameter_for_species(self, species: object) -> SpeciesCarbonParameter:
        """Returns carbon parameters for a species label."""
        normalized_species = self.normalize_species_name(species)
        try:
            return self.species_parameters[normalized_species]
        except KeyError as exc:
            raise ValueError(
                f"No carbon parameters were defined for species '{normalized_species}'."
            ) from exc

    def alpha_for_species(self, species: object, units: str = "MgC") -> float:
        """Returns the species conversion coefficient.

        Parameters
        ----------
        species:
            Species label.
        units:
            ``"MgC"`` for Mg C m-3, or ``"MgCO2e"`` for Mg CO2e m-3.
        """
        parameter = self.parameter_for_species(species)
        units_normalized = units.strip().lower()

        if units_normalized in {"mgc", "c", "carbon"}:
            return parameter.alpha_MgC_m3

        if units_normalized in {"mgco2e", "co2e", "co2eq", "co2"}:
            return parameter.alpha_MgCO2e_m3

        raise ValueError("units must be either 'MgC' or 'MgCO2e'.")


    def add_to_dataframe(self, df: pd.DataFrame, inplace: bool = False) -> pd.DataFrame:
        """Adds carbon accounting columns to one stand-policy DataFrame."""
        required_columns = [
            self.volume_column,
            self.harvest_column,
            self.species_column,
        ]
        missing = [column for column in required_columns if column not in df.columns]
        if missing:
            raise KeyError(
                "The DataFrame is missing required columns for carbon accounting: "
                + ", ".join(missing)
            )

        out = df if inplace else df.copy()

        # Compute differences in temporal order. Restore the original row order
        # before returning, in case the input was not sorted by period.
        original_index = out.index
        if self.period_column in out.columns:
            out = out.sort_values(self.period_column).copy()

        volume_pre = pd.to_numeric(out[self.volume_column], errors="coerce").fillna(0.0)
        removed_volume = pd.to_numeric(out[self.harvest_column], errors="coerce").fillna(0.0)

        if (volume_pre < -self.operation_tolerance).any():
            raise ValueError(f"Column '{self.volume_column}' contains negative volumes.")

        if (removed_volume < -self.operation_tolerance).any():
            raise ValueError(f"Column '{self.harvest_column}' contains negative removed volumes.")

        volume_pre = volume_pre.clip(lower=0.0)
        removed_volume = removed_volume.clip(lower=0.0)

        # bioOPT is the removed volume. Post-operation standing volume is what
        # remains in the live above-ground biomass pool.
        volume_post = (volume_pre - removed_volume).clip(lower=0.0)

        alpha_mgc = out[self.species_column].apply(
            lambda species: self.alpha_for_species(species, units="MgC")
        )
        alpha_co2e = out[self.species_column].apply(
            lambda species: self.alpha_for_species(species, units="MgCO2e")
        )

        out["CarbonAlpha_MgC_m3"] = alpha_mgc
        out["CarbonAlpha_MgCO2e_m3"] = alpha_co2e

        out["VolumePreOperation_m3"] = volume_pre
        out["RemovedVolume_m3"] = removed_volume
        out["VolumePostOperation_m3"] = volume_post

        out["CarbonStockPre_MgC"] = volume_pre * alpha_mgc
        out["RemovedCarbon_MgC"] = removed_volume * alpha_mgc
        out["CarbonStockPost_MgC"] = volume_post * alpha_mgc

        out["CarbonStockPre_MgCO2e"] = volume_pre * alpha_co2e
        out["RemovedCarbon_MgCO2e"] = removed_volume * alpha_co2e
        out["CarbonStockPost_MgCO2e"] = volume_post * alpha_co2e

        # Net change in post-operation carbon stock.
        carb_seq_mgc = out["CarbonStockPost_MgC"].diff()
        carb_seq_co2e = out["CarbonStockPost_MgCO2e"].diff()

        # Operational mask based on removed volume, not on the carbon value.
        operation_mask = removed_volume.abs() > self.operation_tolerance

        # Special case: first simulated period.
        #
        # If there is no operation in the first period, there is no previous
        # simulated post-operation stock, so we use first_period_sequestration.
        #
        # If there is an operation in the first period, assigning zero would hide
        # the immediate carbon-stock reduction. Therefore:
        #
        # CarbSeq_1 = CarbonStockPost_1 - CarbonStockPre_1 = -RemovedCarbon_1
        if len(out) > 0:
            if bool(operation_mask.iloc[0]):
                carb_seq_mgc.iloc[0] = (
                    out["CarbonStockPost_MgC"].iloc[0]
                    - out["CarbonStockPre_MgC"].iloc[0]
                )
                carb_seq_co2e.iloc[0] = (
                    out["CarbonStockPost_MgCO2e"].iloc[0]
                    - out["CarbonStockPre_MgCO2e"].iloc[0]
                )
            else:
                carb_seq_mgc.iloc[0] = self.first_period_sequestration
                carb_seq_co2e.iloc[0] = self.first_period_sequestration * CO2E_FACTOR

        out["CarbSeq_MgC"] = carb_seq_mgc
        out["CarbSeq_MgCO2e"] = carb_seq_co2e

        # Optimization-aligned columns: only periods with a real operation keep
        # the carbon-stock change. Negative values are intentionally preserved.
        out["CarbSeqOPT"] = np.where(operation_mask, out["CarbSeq_MgC"], 0.0)
        out["CarbEqvOPT"] = np.where(operation_mask, out["CarbSeq_MgCO2e"], 0.0)

        if self.rounding is not None:
            columns_to_round = [
                "CarbonAlpha_MgC_m3",
                "CarbonAlpha_MgCO2e_m3",
                "VolumePreOperation_m3",
                "RemovedVolume_m3",
                "VolumePostOperation_m3",
                "CarbonStockPre_MgC",
                "RemovedCarbon_MgC",
                "CarbonStockPost_MgC",
                "CarbonStockPre_MgCO2e",
                "RemovedCarbon_MgCO2e",
                "CarbonStockPost_MgCO2e",
                "CarbSeq_MgC",
                "CarbSeq_MgCO2e",
                "CarbSeqOPT",
                "CarbEqvOPT",
            ]
            out[columns_to_round] = out[columns_to_round].round(self.rounding)

        if self.period_column in out.columns:
            out = out.loc[original_index]

        return out


    def add_to_bosque(
        self,
        bosque: Iterable[pd.DataFrame],
        inplace: bool = False,
    ) -> List[pd.DataFrame]:
        """Adds carbon accounting columns to every DataFrame in ``bosque``."""
        return [self.add_to_dataframe(df, inplace=inplace) for df in bosque]

    def summarize(self, bosque: Iterable[pd.DataFrame]) -> pd.DataFrame:
        """Returns one summary row per stand-policy trajectory.

        The summary includes initial/final post-operation stocks, net change,
        cumulative post-operation stock over time, and total removed carbon.
        """
        rows = []

        for df in bosque:
            if "CarbonStockPost_MgC" not in df.columns:
                df = self.add_to_dataframe(df)

            sorted_df = df.sort_values(self.period_column) if self.period_column in df.columns else df
            first = sorted_df.iloc[0]
            last = sorted_df.iloc[-1]

            row = {
                "id_rodal": first.get(self.stand_column, np.nan),
                "politica": first.get(self.policy_column, np.nan),
                "Especie": first.get(self.species_column, np.nan),
                "initial_carbon_stock_post_MgC": first["CarbonStockPost_MgC"],
                "final_carbon_stock_post_MgC": last["CarbonStockPost_MgC"],
                "net_carbon_stock_change_MgC": last["CarbonStockPost_MgC"]
                - first["CarbonStockPost_MgC"],
                "stock_time_carbon_MgC": sorted_df["CarbonStockPost_MgC"].sum(),
                "total_period_change_MgC": sorted_df["CarbSeq_MgC"].sum(),
                "total_removed_carbon_MgC": sorted_df["RemovedCarbon_MgC"].sum(),
                "initial_carbon_stock_post_MgCO2e": first["CarbonStockPost_MgCO2e"],
                "final_carbon_stock_post_MgCO2e": last["CarbonStockPost_MgCO2e"],
                "net_carbon_stock_change_MgCO2e": last["CarbonStockPost_MgCO2e"]
                - first["CarbonStockPost_MgCO2e"],
                "stock_time_carbon_MgCO2e": sorted_df["CarbonStockPost_MgCO2e"].sum(),
                "total_period_change_MgCO2e": sorted_df["CarbSeq_MgCO2e"].sum(),
                "total_removed_carbon_MgCO2e": sorted_df["RemovedCarbon_MgCO2e"].sum(),
            }
            rows.append(row)

        summary = pd.DataFrame(rows)
        if self.rounding is not None and not summary.empty:
            numeric_columns = summary.select_dtypes(include=["number"]).columns
            summary[numeric_columns] = summary[numeric_columns].round(self.rounding)

        return summary


    def opt_period_dict(
        self,
        bosque: Iterable[pd.DataFrame],
        column: str = "CarbSeqOPT",
        include_zeros: bool = False,
        reference_keys: Optional[Iterable[Tuple[int, object, object, object]]] = None,
    ) -> Dict[Tuple[int, object, object, object], float]:
        """Build a period-indexed carbon dictionary for optimization.

        Output structure:
            {(period, species, policy, stand_id): value}

        The default exported column is CarbSeqOPT, i.e., the net change in
        post-operation above-ground live carbon stock in Mg C.

        The filtering criterion is bioOPT > 0, not the carbon value itself.
        Therefore, the carbon dictionary can be aligned one-to-one with
        treemun's biomass optimization dictionary.

        If reference_keys is provided, the output is forced to use exactly
        those keys. This guarantees that:

            keys(carbon_estimada) == keys(biomasa_estimada)
        """
        values: Dict[Tuple[int, object, object, object], float] = {}

        for df in bosque:
            if column not in df.columns:
                df = self.add_to_dataframe(df)

            required_columns = [
                self.period_column,
                self.species_column,
                self.policy_column,
                self.stand_column,
                self.harvest_column,
                column,
            ]

            missing = [c for c in required_columns if c not in df.columns]
            if missing:
                raise KeyError(
                    "The DataFrame is missing required columns for the carbon "
                    "optimization dictionary: " + ", ".join(missing)
                )

            for _, row in df.iterrows():
                removed_volume = float(row[self.harvest_column])
                is_operation = abs(removed_volume) > self.operation_tolerance

                if not include_zeros and not is_operation:
                    continue

                key = (
                    int(row[self.period_column]),
                    row[self.species_column],
                    row[self.policy_column],
                    row[self.stand_column],
                )

                values[key] = float(row[column])

        if reference_keys is not None:
            reference_keys_list = list(reference_keys)

            missing_keys = [key for key in reference_keys_list if key not in values]

            if missing_keys:
                preview = missing_keys[:10]
                raise KeyError(
                    "Some reference optimization keys were not found in the "
                    "carbon dictionary. Missing examples: "
                    f"{preview}"
                )

            return {key: values[key] for key in reference_keys_list}

        return values


    def final_stock_for_optimization(
        self,
        bosque: Iterable[pd.DataFrame],
        units: str = "MgCO2e",
    ) -> Dict[Tuple[object, object], float]:
        """Returns final post-operation carbon stock by stand-policy."""
        column = self._stock_column_for_units(units)
        values: Dict[Tuple[object, object], float] = {}

        for df in bosque:
            if column not in df.columns:
                df = self.add_to_dataframe(df)

            sorted_df = df.sort_values(self.period_column) if self.period_column in df.columns else df
            last = sorted_df.iloc[-1]
            values[(last[self.stand_column], last[self.policy_column])] = float(last[column])

        return values

    def net_change_for_optimization(
        self,
        bosque: Iterable[pd.DataFrame],
        units: str = "MgCO2e",
    ) -> Dict[Tuple[object, object], float]:
        """Returns final minus initial post-operation carbon stock by stand-policy."""
        column = self._stock_column_for_units(units)
        values: Dict[Tuple[object, object], float] = {}

        for df in bosque:
            if column not in df.columns:
                df = self.add_to_dataframe(df)

            sorted_df = df.sort_values(self.period_column) if self.period_column in df.columns else df
            first = sorted_df.iloc[0]
            last = sorted_df.iloc[-1]
            values[(last[self.stand_column], last[self.policy_column])] = float(
                last[column] - first[column]
            )

        return values

    def stock_time_for_optimization(
        self,
        bosque: Iterable[pd.DataFrame],
        units: str = "MgCO2e",
    ) -> Dict[Tuple[object, object], float]:
        """Returns cumulative post-operation carbon stock over time by stand-policy."""
        column = self._stock_column_for_units(units)
        values: Dict[Tuple[object, object], float] = {}

        for df in bosque:
            if column not in df.columns:
                df = self.add_to_dataframe(df)

            first = df.iloc[0]
            values[(first[self.stand_column], first[self.policy_column])] = float(
                df[column].sum()
            )

        return values

    @staticmethod
    def _stock_column_for_units(units: str) -> str:
        units_normalized = units.strip().lower()
        if units_normalized in {"mgc", "c", "carbon"}:
            return "CarbonStockPost_MgC"
        if units_normalized in {"mgco2e", "co2e", "co2eq", "co2"}:
            return "CarbonStockPost_MgCO2e"
        raise ValueError("units must be either 'MgC' or 'MgCO2e'.")


# Convenience functions -----------------------------------------------------

def add_carbon_proxy_to_bosque(
    bosque: Iterable[pd.DataFrame],
    inplace: bool = False,
    **kwargs,
) -> List[pd.DataFrame]:
    """Adds carbon accounting columns to a ``bosque`` list.

    Example
    -------
    >>> carbon = add_carbon_proxy_to_bosque(bosque)
    """
    proxy = CarbonSequestrationProxy(**kwargs)
    return proxy.add_to_bosque(bosque, inplace=inplace)


def getCarbon4Opti(
    bosque: Iterable[pd.DataFrame],
    column: str = "CarbEqvOPT",
    include_zeros: bool = False,
    **kwargs,
) -> Dict[Tuple[int, object, object, object], float]:
    """Builds an optimization dictionary from a carbon column.

    By default, this returns ``CarbEqvOPT`` values, i.e., Mg CO2e net changes in
    post-operation standing live carbon stock only for operational periods.

    Negative values are retained because they are meaningful for carbon-stock
    reductions caused by thinning or harvest.
    """
    proxy = CarbonSequestrationProxy(**kwargs)
    return proxy.opt_period_dict(
        bosque=bosque,
        column=column,
        include_zeros=include_zeros,
    )


from __future__ import annotations

import argparse
from pathlib import Path
from textwrap import dedent

import nbformat as nbf
from nbformat.validator import validate


BENCHMARK_SOURCE_CANDIDATES = (
    "Treemun_2_0_0_surrogate_vs_source_tables_benchmark.ipynb",
    "/mnt/data/Treemun_2_0_0_surrogate_vs_source_tables_benchmark.ipynb",
)

FINAL_BENCHMARK_NAME = (
    "Treemun_2_0_0_surrogate_vs_source_tables_benchmark_final.ipynb"
)
SOLVER_BENCHMARK_NAME = (
    "Treemun_2_0_0_biobjective_solver_benchmark_105_stands.ipynb"
)


def code(source: str, *, tags: list[str] | None = None):
    cell = nbf.v4.new_code_cell(dedent(source).strip())
    if tags:
        cell.metadata["tags"] = tags
    return cell


def markdown(source: str, *, tags: list[str] | None = None):
    cell = nbf.v4.new_markdown_cell(dedent(source).strip())
    if tags:
        cell.metadata["tags"] = tags
    return cell


def resolve_existing_path(candidates: list[Path] | tuple[Path, ...]) -> Path:
    for candidate in candidates:
        candidate = candidate.expanduser().resolve()
        if candidate.exists():
            return candidate
    checked = "\n".join(f"  - {path}" for path in candidates)
    raise FileNotFoundError(f"No source notebook was found. Checked:\n{checked}")


def final_visualization_cells():
    tag = ["final-benchmark-visuals"]
    return [
        markdown(
            r"""
            ## 17. Final benchmark visualizations

            This section consolidates the figures needed to close the benchmark.
            The main comparison is the annual harvested dry-biomass variable
            \(H_t\) obtained from the independently optimized surrogate and
            source-table representations. Additional figures diagnose curve
            fidelity, cumulative harvest, policy agreement, cross-evaluated NPV,
            and policy transitions.
            """,
            tags=tag,
        ),
        code(
            r"""
            FINAL_FIGURE_DIRECTORY = OUTPUT_DIRECTORY / "figures_final"
            FINAL_FIGURE_DIRECTORY.mkdir(parents=True, exist_ok=True)

            plt.rcParams.update(
                {
                    "figure.dpi": 110,
                    "savefig.dpi": 300,
                    "axes.grid": True,
                    "grid.alpha": 0.25,
                    "font.size": 11,
                }
            )

            print("Final benchmark figures:", FINAL_FIGURE_DIRECTORY)
            """,
            tags=tag,
        ),
        markdown(
            "### 17.1 Annual harvested biomass under each optimized representation",
            tags=tag,
        ),
        code(
            r"""
            # Primary benchmark figure: each representation is optimized and
            # evaluated using its own biomass engine under identical NPV settings.
            fig, axis = plt.subplots(figsize=(13, 6.5))
            axis.plot(
                annual_harvest_comparison["period"],
                annual_harvest_comparison[
                    "surrogate_growth_surrogate_solution_t"
                ],
                marker="o",
                linewidth=2,
                label="Treemün surrogate functions",
            )
            axis.plot(
                annual_harvest_comparison["period"],
                annual_harvest_comparison[
                    "table_growth_table_solution_t"
                ],
                marker="s",
                linewidth=2,
                label="Original source tables",
            )
            axis.set_xlabel("Planning period")
            axis.set_ylabel("Harvested dry biomass (t)")
            axis.set_title(
                "Annual harvested dry biomass under the two optimized models"
            )
            axis.legend()
            fig.tight_layout()
            for suffix in ("png", "pdf"):
                fig.savefig(
                    FINAL_FIGURE_DIRECTORY
                    / f"benchmark_annual_harvest_main.{suffix}",
                    bbox_inches="tight",
                )
            plt.show()

            display(annual_harvest_summary)
            """,
            tags=tag,
        ),
        markdown(
            "### 17.2 Annual and cumulative harvest deviations",
            tags=tag,
        ),
        code(
            r"""
            fig, axis = plt.subplots(figsize=(13, 5.5))
            axis.bar(
                annual_harvest_comparison["period"],
                annual_harvest_comparison["main_schedule_difference_t"],
            )
            axis.axhline(0.0, linewidth=1)
            axis.set_xlabel("Planning period")
            axis.set_ylabel("Surrogate minus table harvest (t)")
            axis.set_title("Annual harvested-biomass deviation")
            fig.tight_layout()
            for suffix in ("png", "pdf"):
                fig.savefig(
                    FINAL_FIGURE_DIRECTORY
                    / f"benchmark_annual_harvest_difference.{suffix}",
                    bbox_inches="tight",
                )
            plt.show()

            cumulative_harvest = annual_harvest_comparison[
                [
                    "period",
                    "surrogate_growth_surrogate_solution_t",
                    "table_growth_table_solution_t",
                ]
            ].copy()
            cumulative_harvest["surrogate_cumulative_t"] = cumulative_harvest[
                "surrogate_growth_surrogate_solution_t"
            ].cumsum()
            cumulative_harvest["table_cumulative_t"] = cumulative_harvest[
                "table_growth_table_solution_t"
            ].cumsum()
            cumulative_harvest["cumulative_difference_t"] = (
                cumulative_harvest["surrogate_cumulative_t"]
                - cumulative_harvest["table_cumulative_t"]
            )

            fig, axis = plt.subplots(figsize=(13, 6))
            axis.plot(
                cumulative_harvest["period"],
                cumulative_harvest["surrogate_cumulative_t"],
                linewidth=2,
                label="Treemün surrogate functions",
            )
            axis.plot(
                cumulative_harvest["period"],
                cumulative_harvest["table_cumulative_t"],
                linewidth=2,
                label="Original source tables",
            )
            axis.set_xlabel("Planning period")
            axis.set_ylabel("Cumulative harvested dry biomass (t)")
            axis.set_title("Cumulative harvested dry biomass")
            axis.legend()
            fig.tight_layout()
            for suffix in ("png", "pdf"):
                fig.savefig(
                    FINAL_FIGURE_DIRECTORY
                    / f"benchmark_cumulative_harvest.{suffix}",
                    bbox_inches="tight",
                )
            plt.show()

            cumulative_harvest.to_csv(
                OUTPUT_DIRECTORY / "cumulative_harvest_comparison.csv",
                index=False,
            )
            """,
            tags=tag,
        ),
        markdown(
            "### 17.3 Source-table biomass versus surrogate predictions",
            tags=tag,
        ),
        code(
            r"""
            minimum_biomass = float(
                min(
                    curve_comparison["source_dry_biomass_t_ha"].min(),
                    curve_comparison["surrogate_dry_biomass_t_ha"].min(),
                )
            )
            maximum_biomass = float(
                max(
                    curve_comparison["source_dry_biomass_t_ha"].max(),
                    curve_comparison["surrogate_dry_biomass_t_ha"].max(),
                )
            )

            fig, axis = plt.subplots(figsize=(7.5, 7.5))
            for species, group in curve_comparison.groupby("species"):
                axis.scatter(
                    group["source_dry_biomass_t_ha"],
                    group["surrogate_dry_biomass_t_ha"],
                    alpha=0.65,
                    label=species,
                )
            axis.plot(
                [minimum_biomass, maximum_biomass],
                [minimum_biomass, maximum_biomass],
                linestyle="--",
                linewidth=1.5,
                label="1:1 reference",
            )
            axis.set_xlabel("Original table biomass (t dry biomass/ha)")
            axis.set_ylabel("Surrogate prediction (t dry biomass/ha)")
            axis.set_title("Curve-level fidelity at source-table observations")
            axis.set_aspect("equal", adjustable="box")
            axis.legend()
            fig.tight_layout()
            for suffix in ("png", "pdf"):
                fig.savefig(
                    FINAL_FIGURE_DIRECTORY
                    / f"benchmark_curve_fidelity_scatter.{suffix}",
                    bbox_inches="tight",
                )
            plt.show()
            """,
            tags=tag,
        ),
        markdown(
            "### 17.4 Residual behavior across biological age",
            tags=tag,
        ),
        code(
            r"""
            fig, axis = plt.subplots(figsize=(11, 6))
            for species, group in curve_comparison.groupby("species"):
                axis.scatter(
                    group["age"],
                    group["residual_t_ha"],
                    alpha=0.65,
                    label=species,
                )
            axis.axhline(0.0, linewidth=1)
            axis.set_xlabel("Biological age")
            axis.set_ylabel("Surrogate minus source table (t/ha)")
            axis.set_title("Surrogate residuals by biological age")
            axis.legend()
            fig.tight_layout()
            for suffix in ("png", "pdf"):
                fig.savefig(
                    FINAL_FIGURE_DIRECTORY
                    / f"benchmark_residuals_by_age.{suffix}",
                    bbox_inches="tight",
                )
            plt.show()
            """,
            tags=tag,
        ),
        markdown(
            "### 17.5 Decision agreement and cross-evaluated regret",
            tags=tag,
        ),
        code(
            r"""
            agreement_by_species = (
                selected_policy_comparison.groupby("species", as_index=False)
                .agg(
                    stands=("stand_id", "size"),
                    policy_agreement=("same_policy", "mean"),
                    mean_table_regret=(
                        "table_regret_from_surrogate_decision",
                        "mean",
                    ),
                )
            )

            fig, axis = plt.subplots(figsize=(8, 5.5))
            axis.bar(
                agreement_by_species["species"],
                100.0 * agreement_by_species["policy_agreement"],
            )
            axis.set_ylim(0.0, 100.0)
            axis.set_ylabel("Identical selected policies (%)")
            axis.set_title("Stand-level policy agreement by species")
            fig.tight_layout()
            for suffix in ("png", "pdf"):
                fig.savefig(
                    FINAL_FIGURE_DIRECTORY
                    / f"benchmark_policy_agreement_by_species.{suffix}",
                    bbox_inches="tight",
                )
            plt.show()

            cross_evaluation_plot = pd.DataFrame(
                {
                    "case": [
                        "Table optimum\n(table evaluation)",
                        "Surrogate solution\n(table evaluation)",
                        "Surrogate optimum\n(surrogate evaluation)",
                        "Table solution\n(surrogate evaluation)",
                    ],
                    "npv": [
                        table_optimum_npv,
                        table_value_of_surrogate_solution,
                        surrogate_optimum_npv,
                        surrogate_value_of_table_solution,
                    ],
                }
            )

            fig, axis = plt.subplots(figsize=(10, 6))
            axis.bar(
                cross_evaluation_plot["case"],
                cross_evaluation_plot["npv"] / 1_000_000.0,
            )
            axis.set_ylabel("NPV (million constant 2025 USD)")
            axis.set_title("Cross-evaluated optimal and transferred decisions")
            axis.tick_params(axis="x", rotation=12)
            fig.tight_layout()
            for suffix in ("png", "pdf"):
                fig.savefig(
                    FINAL_FIGURE_DIRECTORY
                    / f"benchmark_cross_evaluated_npv.{suffix}",
                    bbox_inches="tight",
                )
            plt.show()

            display(agreement_by_species)
            display(regret_summary)
            """,
            tags=tag,
        ),
        markdown(
            "### 17.6 Policy-transition matrix",
            tags=tag,
        ),
        code(
            r"""
            policy_transition = pd.crosstab(
                selected_policy_comparison["surrogate_selected_policy"],
                selected_policy_comparison["table_selected_policy"],
            )
            all_policies = sorted(
                set(policy_transition.index) | set(policy_transition.columns)
            )
            policy_transition = policy_transition.reindex(
                index=all_policies,
                columns=all_policies,
                fill_value=0,
            )

            fig, axis = plt.subplots(figsize=(10, 9))
            image = axis.imshow(policy_transition.to_numpy(), aspect="auto")
            axis.set_xticks(np.arange(len(all_policies)))
            axis.set_yticks(np.arange(len(all_policies)))
            axis.set_xticklabels(all_policies, rotation=90)
            axis.set_yticklabels(all_policies)
            axis.set_xlabel("Policy selected with original tables")
            axis.set_ylabel("Policy selected with surrogate functions")
            axis.set_title("Selected-policy transition matrix")
            figure_colorbar = fig.colorbar(image, ax=axis)
            figure_colorbar.set_label("Number of stands")
            fig.tight_layout()
            for suffix in ("png", "pdf"):
                fig.savefig(
                    FINAL_FIGURE_DIRECTORY
                    / f"benchmark_policy_transition_matrix.{suffix}",
                    bbox_inches="tight",
                )
            plt.show()

            policy_transition.to_csv(
                OUTPUT_DIRECTORY / "selected_policy_transition_matrix.csv"
            )
            """,
            tags=tag,
        ),
        markdown(
            r"""
            ### Final interpretation

            The annual harvest plot should be interpreted together with the
            decision-regret statistics. Different policy identifiers or annual
            harvest peaks do not necessarily imply a material loss of decision
            quality. The primary decision-fidelity measure remains the NPV regret
            obtained when the surrogate-derived solution is re-evaluated using
            the original source tables.
            """,
            tags=tag,
        ),
    ]


def generate_final_benchmark_notebook(source: Path, output: Path) -> Path:
    notebook = nbf.read(source, as_version=4)

    notebook.cells = [
        cell
        for cell in notebook.cells
        if "final-benchmark-visuals" not in cell.metadata.get("tags", [])
    ]

    insertion_index = len(notebook.cells)
    for index, cell in enumerate(notebook.cells):
        if (
            cell.cell_type == "markdown"
            and cell.source.lstrip().startswith("## Recommended interpretation")
        ):
            insertion_index = index
            break

    cells = final_visualization_cells()
    notebook.cells[insertion_index:insertion_index] = cells
    notebook.metadata.setdefault("kernelspec", {})
    notebook.metadata["kernelspec"].update(
        {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        }
    )
    notebook.metadata.setdefault("language_info", {})
    notebook.metadata["language_info"]["name"] = "python"

    validate(notebook)
    nbf.write(notebook, output)
    return output


def solver_notebook_cells():
    return [
        markdown(
            r"""
            # Treemün 2.0.0: single-core solver benchmark for the 105-stand bi-objective model

            This notebook compares CPLEX, HiGHS, and CBC on exactly the same
            weighted bi-objective model:

            \[
            \max\; 0.5\,\widetilde{NPV} + 0.5\,\widetilde{C},
            \]

            where both objectives use a single common payoff-range
            normalization. The landscape contains all 105 stands. No spatial
            adjacency or green-up constraints are included. Every solve requests
            one solver thread.

            The payoff anchors are computed once with a reference solver and are
            excluded from the timed solver comparison. This ensures that every
            compared solver receives identical objective coefficients.
            """
        ),
        markdown("## 1. Imports and paths"),
        code(
            r"""
            from __future__ import annotations

            from pathlib import Path
            import os
            import platform
            import sys
            import time

            import numpy as np
            import pandas as pd
            import matplotlib.pyplot as plt
            from IPython.display import display

            import pyomo.environ as pyo
            import treemun_sim as tm

            pd.set_option("display.max_columns", 120)
            pd.set_option("display.width", 200)

            WORKING_DIRECTORY = Path.cwd().resolve()


            def first_existing(candidates, label):
                for candidate in candidates:
                    candidate = Path(candidate).expanduser().resolve()
                    if candidate.exists():
                        return candidate
                checked = "\n".join(f"  - {item}" for item in candidates)
                raise FileNotFoundError(
                    f"Could not locate {label}. Checked:\n{checked}"
                )


            PACKAGE_DIRECTORY = Path(tm.__file__).resolve().parent
            PROJECT_ROOT = PACKAGE_DIRECTORY.parent
            STANDS_FILE = first_existing(
                [
                    WORKING_DIRECTORY / "forest_stands.csv",
                    WORKING_DIRECTORY / "examples" / "forest_stands.csv",
                    WORKING_DIRECTORY.parent / "examples" / "forest_stands.csv",
                    PROJECT_ROOT / "examples" / "forest_stands.csv",
                    Path("/mnt/data/benchmark_validation/forest_stands.csv"),
                ],
                "105-stand input file",
            )
            OUTPUT_DIRECTORY = (
                WORKING_DIRECTORY / "outputs_solver_benchmark_105_stands"
            )
            OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

            print("Treemün version:", tm.__version__)
            print("Treemün location:", Path(tm.__file__).resolve())
            print("Python:", sys.version.split()[0])
            print("Platform:", platform.platform())
            print("Visible logical CPUs:", os.cpu_count())
            print("Stand file:", STANDS_FILE)
            print("Output directory:", OUTPUT_DIRECTORY)
            """
        ),
        markdown("## 2. Reproducible benchmark configuration"),
        code(
            r"""
            HORIZON = 30
            DISCOUNT_RATE = 0.08
            RELATIVE_GAP = 0.01

            NPV_WEIGHT = 0.50
            CARBON_WEIGHT = 0.50

            # Fairness requirement: every solver receives exactly one thread.
            SOLVER_THREADS = 1
            SOLVER_TIME_LIMIT_SECONDS = None

            # Repeated solves reduce the effect of timing noise. Set to 1 for a
            # quick demonstration or increase for a formal computational study.
            NUMBER_OF_REPETITIONS = 3
            RUN_UNTIMED_WARMUP = True

            FALLBACK_THINNING_FRACTION = 0.30
            MINIMUM_CURVE_RESIDUAL_FRACTION = 0.10

            SOLVER_INTERFACE_CANDIDATES = {
                "CPLEX": ("cplex",),
                "HiGHS": ("appsi_highs", "highs"),
                "CBC": ("cbc",),
            }

            CHILE_2025_ECONOMIC_PARAMETERS = {
                "revenue_per_dry_t": {
                    tm.PINUS: 44.07,
                    tm.EUCALYPTUS: 43.66,
                },
                "variable_cost_per_dry_t": {
                    tm.PINUS: 0.0,
                    tm.EUCALYPTUS: 0.0,
                },
                "transport_cost_per_dry_t": {
                    tm.PINUS: 15.76,
                    tm.EUCALYPTUS: 10.59,
                },
                "thinning_cost_per_dry_t": {
                    tm.PINUS: 11.03,
                    tm.EUCALYPTUS: 0.0,
                },
                "final_harvest_cost_per_dry_t": {
                    tm.PINUS: 12.61,
                    tm.EUCALYPTUS: 8.47,
                },
                "thinning_cost_per_ha": 0.0,
                "final_harvest_cost_per_ha": 0.0,
                "replanting_cost_per_ha": {
                    tm.PINUS: 684.0,
                    tm.EUCALYPTUS: 716.0,
                },
                "annual_management_cost_per_ha": 15.0,
                "replanting_delay_periods": 0,
                "terminal_value_per_dry_t": {
                    tm.PINUS: 7.85,
                    tm.EUCALYPTUS: 12.30,
                },
            }

            print("NPV weight:", NPV_WEIGHT)
            print("Carbon weight:", CARBON_WEIGHT)
            print("Relative MIP gap:", RELATIVE_GAP)
            print("Threads per solver:", SOLVER_THREADS)
            print("Measured repetitions:", NUMBER_OF_REPETITIONS)
            """
        ),
        markdown("## 3. Detect the available solver interfaces"),
        code(
            r"""
            def interface_is_available(interface_name: str) -> bool:
                try:
                    solver = pyo.SolverFactory(interface_name)
                    return bool(
                        solver is not None
                        and solver.available(exception_flag=False)
                    )
                except Exception:
                    return False


            available_solver_interfaces = {}
            solver_detection_records = []

            for solver_label, candidates in SOLVER_INTERFACE_CANDIDATES.items():
                selected_interface = None
                for candidate in candidates:
                    if interface_is_available(candidate):
                        selected_interface = candidate
                        break
                available_solver_interfaces[solver_label] = selected_interface
                solver_detection_records.append(
                    {
                        "solver": solver_label,
                        "selected_pyomo_interface": selected_interface,
                        "available": selected_interface is not None,
                    }
                )

            solver_availability = pd.DataFrame(solver_detection_records)
            display(solver_availability)

            AVAILABLE_SOLVERS = {
                label: interface
                for label, interface in available_solver_interfaces.items()
                if interface is not None
            }
            if not AVAILABLE_SOLVERS:
                raise RuntimeError(
                    "None of CPLEX, HiGHS, or CBC is available in this environment."
                )

            REFERENCE_SOLVER_LABEL = (
                "CPLEX" if "CPLEX" in AVAILABLE_SOLVERS else next(iter(AVAILABLE_SOLVERS))
            )
            REFERENCE_SOLVER_INTERFACE = AVAILABLE_SOLVERS[REFERENCE_SOLVER_LABEL]

            print("Available benchmark solvers:", AVAILABLE_SOLVERS)
            print(
                "Reference solver for common payoff normalization:",
                REFERENCE_SOLVER_LABEL,
                f"({REFERENCE_SOLVER_INTERFACE})",
            )
            """
        ),
        markdown("## 4. Simulate all 105 stands once"),
        code(
            r"""
            stands = tm.load_stand_table(STANDS_FILE)

            simulation_started = time.perf_counter()
            (
                forest,
                policy_summary,
                ending_stock,
                harvested_by_period,
                carbon_by_period,
            ) = tm.simulate_forest(
                stands_file=STANDS_FILE,
                horizon=HORIZON,
                include_carbon=True,
                return_carbon_for_optimization=True,
                fallback_thinning_fraction=FALLBACK_THINNING_FRACTION,
                minimum_curve_residual_fraction=(
                    MINIMUM_CURVE_RESIDUAL_FRACTION
                ),
            )
            simulation_time_seconds = time.perf_counter() - simulation_started

            print("Input stands:", stands["stand_id"].nunique())
            print("Stand-policy alternatives:", len(forest))
            print("Annual trajectory rows:", sum(len(frame) for frame in forest))
            print(f"Simulation time: {simulation_time_seconds:.3f} s")

            assert stands["stand_id"].nunique() == 105
            assert len({frame.iloc[0]["stand_id"] for frame in forest}) == 105
            """
        ),
        markdown("## 5. Build the common model specification"),
        code(
            r"""
            MODEL_OPTIONS = {
                "policy_summary": policy_summary,
                "ending_dry_wood_by_policy": ending_stock,
                "harvested_dry_wood_by_period": harvested_by_period,
                "horizon": HORIZON,
                "forest": forest,
                "carbon_stock_time_by_period": carbon_by_period,
                "economic_mode": "detailed_cash_flow",
                "economic_parameters": CHILE_2025_ECONOMIC_PARAMETERS,
                "discount_rate": DISCOUNT_RATE,
                "minimum_ending_dry_wood_t": 0.0,
                "minimum_ending_dry_wood_fraction": None,
                "even_flow_mode": "none",
            }

            COMMON_SOLVER_OPTIONS = {
                "relative_gap": RELATIVE_GAP,
                "threads": SOLVER_THREADS,
                "time_limit_seconds": SOLVER_TIME_LIMIT_SECONDS,
                "tee": False,
            }
            """
        ),
        markdown(
            r"""
            ## 6. Compute a single common payoff-range normalization

            These two anchor solves are preparatory and are not included in the
            reported CPLEX–HiGHS–CBC timing comparison. Their only purpose is to
            define common values for \(NPV_{ref}\), \(C_{ref}\), and the two
            payoff ranges.
            """
        ),
        code(
            r"""
            payoff_started = time.perf_counter()
            common_payoff_table = tm.build_biobjective_payoff_table(
                solver_name=REFERENCE_SOLVER_INTERFACE,
                solver_options=COMMON_SOLVER_OPTIONS,
                model_options=MODEL_OPTIONS,
            )
            payoff_wall_time_seconds = time.perf_counter() - payoff_started
            common_normalization = tm.biobjective_normalization_from_payoff(
                common_payoff_table
            )

            display(
                common_payoff_table[
                    [
                        "optimized_for",
                        "economic_value",
                        "carbon_stock_time_tC_year",
                        "solve_time_seconds",
                        "total_model_time_seconds",
                    ]
                ]
            )
            print("Common normalization:")
            for key, value in common_normalization.items():
                print(f"  {key}: {value:,.6f}")
            print(
                "Preparatory payoff wall time (excluded from benchmark):",
                f"{payoff_wall_time_seconds:.3f} s",
            )
            """
        ),
        markdown("## 7. Timed weighted-model solves"),
        code(
            r"""
            def build_identical_weighted_model():
                return tm.build_forest_management_model(
                    **MODEL_OPTIONS,
                    objective="weighted",
                    npv_weight=NPV_WEIGHT,
                    carbon_weight=CARBON_WEIGHT,
                    **common_normalization,
                )


            def selected_policy_key_set(solution) -> frozenset[tuple[str, str]]:
                selected = solution["selected_policies"]
                return frozenset(
                    zip(
                        selected["stand_id"].astype(str),
                        selected["policy"].astype(str),
                    )
                )


            def solve_one_replication(
                solver_label: str,
                solver_interface: str,
                replication: int,
                measured: bool,
            ):
                total_started = time.perf_counter()
                build_started = time.perf_counter()
                model = build_identical_weighted_model()
                measured_build_wall_seconds = time.perf_counter() - build_started

                solve_started = time.perf_counter()
                results = tm.solve_model(
                    model,
                    solver_interface,
                    **COMMON_SOLVER_OPTIONS,
                )
                measured_solve_wall_seconds = time.perf_counter() - solve_started
                measured_total_wall_seconds = time.perf_counter() - total_started
                solution = tm.extract_solution(model, results)

                record = {
                    "solver": solver_label,
                    "pyomo_interface": solver_interface,
                    "replication": replication,
                    "measured": measured,
                    "status": str(results.solver.status),
                    "termination_condition": str(
                        results.solver.termination_condition
                    ),
                    "threads_requested": SOLVER_THREADS,
                    "relative_gap_requested": RELATIVE_GAP,
                    "npv_weight": NPV_WEIGHT,
                    "carbon_weight": CARBON_WEIGHT,
                    "economic_value": solution["economic_value"],
                    "carbon_stock_time_tC_year": solution[
                        "carbon_stock_time_tC_year"
                    ],
                    "normalized_npv_value": solution[
                        "normalized_npv_value"
                    ],
                    "normalized_carbon_value": solution[
                        "normalized_carbon_value"
                    ],
                    "weighted_normalized_objective": (
                        NPV_WEIGHT * solution["normalized_npv_value"]
                        + CARBON_WEIGHT
                        * solution["normalized_carbon_value"]
                    ),
                    "ending_dry_wood_t": solution["ending_dry_wood_t"],
                    "reported_model_build_time_seconds": solution[
                        "model_build_time_seconds"
                    ],
                    "reported_solve_time_seconds": solution[
                        "solve_time_seconds"
                    ],
                    "reported_total_model_time_seconds": solution[
                        "total_model_time_seconds"
                    ],
                    "measured_build_wall_seconds": (
                        measured_build_wall_seconds
                    ),
                    "measured_solve_wall_seconds": (
                        measured_solve_wall_seconds
                    ),
                    "measured_total_wall_seconds": (
                        measured_total_wall_seconds
                    ),
                    "number_of_selected_policies": len(
                        solution["selected_policies"]
                    ),
                }
                return record, selected_policy_key_set(solution)


            if RUN_UNTIMED_WARMUP:
                for solver_label, solver_interface in AVAILABLE_SOLVERS.items():
                    print(f"Warm-up: {solver_label} ({solver_interface})")
                    solve_one_replication(
                        solver_label,
                        solver_interface,
                        replication=0,
                        measured=False,
                    )

            benchmark_records = []
            selected_policy_sets = {}

            for solver_label, solver_interface in AVAILABLE_SOLVERS.items():
                for replication in range(1, NUMBER_OF_REPETITIONS + 1):
                    print(
                        f"Measured solve {replication}/{NUMBER_OF_REPETITIONS}: "
                        f"{solver_label} ({solver_interface})"
                    )
                    record, policy_set = solve_one_replication(
                        solver_label,
                        solver_interface,
                        replication=replication,
                        measured=True,
                    )
                    benchmark_records.append(record)
                    selected_policy_sets[(solver_label, replication)] = policy_set

            solver_runs = pd.DataFrame(benchmark_records)
            display(solver_runs)
            solver_runs.to_csv(
                OUTPUT_DIRECTORY / "solver_benchmark_individual_runs.csv",
                index=False,
            )
            """
        ),
        markdown("## 8. Timing and solution-consistency summary"),
        code(
            r"""
            reference_policy_set = selected_policy_sets[
                (REFERENCE_SOLVER_LABEL, 1)
            ]
            reference_objective = float(
                solver_runs.loc[
                    (solver_runs["solver"] == REFERENCE_SOLVER_LABEL)
                    & (solver_runs["replication"] == 1),
                    "weighted_normalized_objective",
                ].iloc[0]
            )

            policy_agreement_records = []
            for (solver_label, replication), policy_set in selected_policy_sets.items():
                intersection = len(reference_policy_set & policy_set)
                union = len(reference_policy_set | policy_set)
                policy_agreement_records.append(
                    {
                        "solver": solver_label,
                        "replication": replication,
                        "policy_agreement_with_reference": (
                            intersection / len(reference_policy_set)
                        ),
                        "policy_jaccard_with_reference": (
                            intersection / union if union else 1.0
                        ),
                        "policy_hamming_distance": (
                            len(reference_policy_set - policy_set)
                            + len(policy_set - reference_policy_set)
                        ),
                    }
                )

            policy_agreement = pd.DataFrame(policy_agreement_records)
            solver_runs = solver_runs.merge(
                policy_agreement,
                on=["solver", "replication"],
                validate="one_to_one",
            )
            solver_runs["weighted_objective_difference_from_reference"] = (
                solver_runs["weighted_normalized_objective"]
                - reference_objective
            )

            solver_summary = (
                solver_runs.groupby(
                    ["solver", "pyomo_interface"], as_index=False
                )
                .agg(
                    repetitions=("replication", "size"),
                    successful_runs=(
                        "termination_condition",
                        lambda series: int(
                            series.str.lower().isin(
                                ["optimal", "maxTimeLimit".lower()]
                            ).sum()
                        ),
                    ),
                    mean_solve_time_seconds=(
                        "measured_solve_wall_seconds",
                        "mean",
                    ),
                    median_solve_time_seconds=(
                        "measured_solve_wall_seconds",
                        "median",
                    ),
                    std_solve_time_seconds=(
                        "measured_solve_wall_seconds",
                        "std",
                    ),
                    minimum_solve_time_seconds=(
                        "measured_solve_wall_seconds",
                        "min",
                    ),
                    maximum_solve_time_seconds=(
                        "measured_solve_wall_seconds",
                        "max",
                    ),
                    mean_total_time_seconds=(
                        "measured_total_wall_seconds",
                        "mean",
                    ),
                    median_total_time_seconds=(
                        "measured_total_wall_seconds",
                        "median",
                    ),
                    economic_value=("economic_value", "median"),
                    carbon_stock_time_tC_year=(
                        "carbon_stock_time_tC_year",
                        "median",
                    ),
                    weighted_normalized_objective=(
                        "weighted_normalized_objective",
                        "median",
                    ),
                    policy_agreement_with_reference=(
                        "policy_agreement_with_reference",
                        "mean",
                    ),
                    policy_hamming_distance=(
                        "policy_hamming_distance",
                        "max",
                    ),
                )
            )

            solver_summary["relative_solve_time_to_fastest"] = (
                solver_summary["median_solve_time_seconds"]
                / solver_summary["median_solve_time_seconds"].min()
            )

            display(solver_summary.sort_values("median_solve_time_seconds"))
            solver_runs.to_csv(
                OUTPUT_DIRECTORY / "solver_benchmark_individual_runs.csv",
                index=False,
            )
            solver_summary.to_csv(
                OUTPUT_DIRECTORY / "solver_benchmark_summary.csv",
                index=False,
            )
            """
        ),
        markdown("## 9. Solver-comparison figures"),
        code(
            r"""
            ordered_summary = solver_summary.sort_values(
                "median_solve_time_seconds"
            ).reset_index(drop=True)

            fig, axis = plt.subplots(figsize=(8, 5.5))
            error_values = ordered_summary["std_solve_time_seconds"].fillna(0.0)
            axis.bar(
                ordered_summary["solver"],
                ordered_summary["median_solve_time_seconds"],
                yerr=error_values,
                capsize=5,
            )
            axis.set_ylabel("Median solve wall time (s)")
            axis.set_title(
                "Single-core weighted bi-objective solve time (0.5 NPV / 0.5 carbon)"
            )
            fig.tight_layout()
            for suffix in ("png", "pdf"):
                fig.savefig(
                    OUTPUT_DIRECTORY / f"solver_median_solve_time.{suffix}",
                    bbox_inches="tight",
                )
            plt.show()

            fig, axis = plt.subplots(figsize=(8, 5.5))
            axis.bar(
                ordered_summary["solver"],
                ordered_summary["median_total_time_seconds"],
            )
            axis.set_ylabel("Median build + solve wall time (s)")
            axis.set_title("Single-core total model time")
            fig.tight_layout()
            for suffix in ("png", "pdf"):
                fig.savefig(
                    OUTPUT_DIRECTORY / f"solver_median_total_time.{suffix}",
                    bbox_inches="tight",
                )
            plt.show()

            fig, axis = plt.subplots(figsize=(8, 5.5))
            axis.scatter(
                solver_runs["solver"],
                solver_runs["weighted_normalized_objective"],
            )
            axis.axhline(reference_objective, linestyle="--", linewidth=1)
            axis.set_ylabel("Weighted normalized objective")
            axis.set_title("Objective-value consistency across solvers")
            fig.tight_layout()
            for suffix in ("png", "pdf"):
                fig.savefig(
                    OUTPUT_DIRECTORY
                    / f"solver_weighted_objective_consistency.{suffix}",
                    bbox_inches="tight",
                )
            plt.show()

            fig, axis = plt.subplots(figsize=(8, 5.5))
            axis.bar(
                ordered_summary["solver"],
                100.0
                * ordered_summary["policy_agreement_with_reference"],
            )
            axis.set_ylim(0.0, 100.0)
            axis.set_ylabel("Policy agreement with reference (%)")
            axis.set_title("Selected-policy agreement across solvers")
            fig.tight_layout()
            for suffix in ("png", "pdf"):
                fig.savefig(
                    OUTPUT_DIRECTORY / f"solver_policy_agreement.{suffix}",
                    bbox_inches="tight",
                )
            plt.show()
            """
        ),
        markdown("## 10. Reproducibility metadata and interpretation"),
        code(
            r"""
            scheduler_metadata = {
                variable: os.getenv(variable)
                for variable in (
                    "SLURM_CPUS_PER_TASK",
                    "SLURM_CPUS_ON_NODE",
                    "PBS_NP",
                    "NSLOTS",
                )
            }
            reproducibility_metadata = pd.DataFrame(
                [
                    {
                        "treemun_version": tm.__version__,
                        "python_version": sys.version.split()[0],
                        "platform": platform.platform(),
                        "visible_logical_cpus": os.cpu_count(),
                        "threads_requested_per_solver": SOLVER_THREADS,
                        "relative_gap": RELATIVE_GAP,
                        "time_limit_seconds": SOLVER_TIME_LIMIT_SECONDS,
                        "number_of_repetitions": NUMBER_OF_REPETITIONS,
                        "warmup_excluded": RUN_UNTIMED_WARMUP,
                        "reference_solver": REFERENCE_SOLVER_LABEL,
                        "reference_interface": REFERENCE_SOLVER_INTERFACE,
                        **scheduler_metadata,
                    }
                ]
            )
            display(reproducibility_metadata.T.rename(columns={0: "value"}))
            reproducibility_metadata.to_csv(
                OUTPUT_DIRECTORY / "solver_benchmark_metadata.csv",
                index=False,
            )

            print("Interpretation")
            print("--------------")
            print(
                "1. Compare median solve times because every solver receives "
                "the same weighted model, normalization, relative gap, and one core."
            )
            print(
                "2. Verify objective values and selected policies before "
                "interpreting speed differences."
            )
            print(
                "3. The preparatory payoff-anchor time is excluded because it "
                "is common to all compared weighted solves."
            )
            print(
                "4. For a formal computational experiment, run this notebook "
                "on an otherwise idle node and report hardware, solver versions, "
                "license mode, and scheduler allocation."
            )
            print("\nOutputs written to:", OUTPUT_DIRECTORY)
            """
        ),
    ]


def generate_solver_benchmark_notebook(output: Path) -> Path:
    notebook = nbf.v4.new_notebook()
    notebook.cells = solver_notebook_cells()
    notebook.metadata = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "pygments_lexer": "ipython3",
        },
    }
    validate(notebook)
    nbf.write(notebook, output)
    return output


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Generate the final Treemün benchmark notebooks."
    )
    parser.add_argument(
        "--benchmark-source",
        type=Path,
        default=None,
        help=(
            "Existing surrogate-versus-table benchmark notebook to extend. "
            "If omitted, common filenames are searched."
        ),
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path.cwd(),
        help="Directory where both generated notebooks are written.",
    )
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    output_directory = arguments.output_directory.expanduser().resolve()
    output_directory.mkdir(parents=True, exist_ok=True)

    if arguments.benchmark_source is not None:
        benchmark_source = arguments.benchmark_source.expanduser().resolve()
        if not benchmark_source.exists():
            raise FileNotFoundError(benchmark_source)
    else:
        benchmark_source = resolve_existing_path(
            tuple(Path(item) for item in BENCHMARK_SOURCE_CANDIDATES)
        )

    final_benchmark = output_directory / FINAL_BENCHMARK_NAME
    solver_benchmark = output_directory / SOLVER_BENCHMARK_NAME

    generate_final_benchmark_notebook(benchmark_source, final_benchmark)
    generate_solver_benchmark_notebook(solver_benchmark)

    print("Generated:")
    print(" -", final_benchmark)
    print(" -", solver_benchmark)


if __name__ == "__main__":
    main()

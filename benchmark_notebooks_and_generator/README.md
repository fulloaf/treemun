# Treemün 2.0.0 benchmark materials

This directory contains the authoritative benchmark notebooks and the original source tables used to derive and validate the Treemün surrogate growth functions.

## Retained notebooks

- `Treemun_2_0_0_surrogate_vs_source_tables_benchmark_Mg_harmonized.ipynb`: compares the harmonized Mg-based surrogate functions against the original source tables.
- `Treemun_2_0_0_biobjective_solver_benchmark_105_stands_Mg_harmonized.ipynb`: compares supported solvers on the harmonized 105-stand bi-objective benchmark.

## Original source tables

- `DatosArmonizados_Plantaciones_VFinal.xlsm`
- `DatosArmonizados_Plantaciones_VFinal.csv`

These two files are the original harmonized plantation data tables used to generate the surrogate functions. They are retained as provenance data and should not be replaced by notebook-generated outputs.

## Generator

`generate_treemun_benchmark_notebooks.py` is retained as a development helper and provenance artifact. The two notebooks listed above are the authoritative release notebooks.

Generated figures, CSV result tables, solver logs, and output directories are intentionally excluded from the source release. Running the notebooks recreates their corresponding `outputs_*` directories locally; those directories are ignored by Git.

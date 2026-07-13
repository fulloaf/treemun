# Spatial Simulation with Shapefiles - treemun-sim

This guide demonstrates how to integrate treemun-sim simulations with spatial data using shapefiles for GIS analysis and visualization.

## ⚠️ Important Note

**This spatial analysis module is only available for user-provided forest stands** loaded from CSV files using the `archivo_rodales` parameter. 

**Random forest generation (`num_rodales`) does not support spatial analysis** since randomly generated stands don't have associated geometries.

---

## 📋 Table of Contents

- [Installation](#installation)
- [Requirements](#requirements)
- [Complete Workflow](#complete-workflow)
- [Function Reference](#function-reference)
- [Output Format](#output-format)
- [QGIS Visualization](#qgis-visualization)
- [Troubleshooting](#troubleshooting)

---

## Installation

### Basic Installation
```bash
pip install treemun-sim
```

### With Spatial Analysis Support
```bash
pip install treemun-sim[spatial]
```

This installs the required dependencies:
- `geopandas` - for shapefile handling
- `shapely` - for geometric operations

---

## Requirements

To use spatial analysis, you need:

1. **User-provided stand data** - CSV file with forest stand attributes
2. **Shapefile with geometries** - `.shp` file with polygon geometries for each stand
3. **Matching IDs** - `id_rodal` field must match between CSV and shapefile

### Example File Structure

This is an example of how a user might organize their project files when using treemun spatial analysis:

```
my_project/                         # User's project folder
├── data/
│   ├── forest_stands.csv          # User's stand attributes
│   ├── landscape.shp               # User's geometries (required)
│   ├── landscape.shx               # (required)
│   ├── landscape.dbf               # (required)
│   └── landscape.prj               # (required)
└── scripts/
    └── my_analysis.py              # User's Python script (uses treemun)
```

**Note:** The `my_analysis.py` file is created by the user - it's where you write your Python code that imports and uses treemun-sim.

---

## Complete Workflow

### Step 1: Simulate Forest Growth

⚠️ **Important:** Use `archivo_rodales` parameter (not `num_rodales`) to load stands from file.

```python
import treemun_sim as tm

# Load forest stands from CSV file
forest, summary, final_biomass, collected_biomass = tm.simular_bosque(
    archivo_rodales="path_to_your_file/forest_stands.csv",
    horizonte=30,
    policies_pino=[(10, 20), (11, 22), (12, 24)],      # 3 policies for Pinus
    policies_eucalyptus=[(9,), (10,), (11,), (12,)]    # 4 policies for Eucalyptus
)
```

**Input CSV format:**
```csv
id_rodal,hectareas,especie,edad_inicial,zona,site_index,manejo,condicion,densidad_inicial
stand1,10.5,Pinus,5,6,32,Intensivo,PostRaleo1250-700,1250
stand2,8.3,Eucapyltus,3,1,28,NA,SinManejo,1250
stand3,12.1,Pinus,7,7,29,Intensivo2,PostRaleo1250-700,1250
```

---

### Step 2: Export All Simulations to Shapefile

Export complete simulation results with biomass values for **all policies** and **all time periods**:

```python
# Export all simulated policies to shapefile
gdf_sim = tm.export_simulation_to_shapefile(
    forest=forest,
    summary=summary,
    shapefile_input="path_to_your_file/landscape.shp",
    shapefile_output="path_to_your_file/landscape_simulated.shp"
)
```

**Generated attributes:**
```
id_rodal, geometry, especie, hectareas, edad_ini,
bio_P1_t1, bio_P1_t2, ..., bio_P1_t30,   # Policy 1, all periods
bio_P2_t1, bio_P2_t2, ..., bio_P2_t30,   # Policy 2, all periods
bio_P3_t1, bio_P3_t2, ..., bio_P3_t30    # Policy 3, all periods
```

**Use this for:**
- Comparing different management policies
- Creating temporal animations in QGIS
- Analyzing biomass evolution over time
- Exploratory spatial analysis

---

### Step 3: Create Optimization Model

Define the forest management optimization problem:

```python
# Create optimization model
model = tm.forest_management_optimization_model(
    bosque=forest,
    a_i_j_T=final_biomass,
    a_i_j_t=collected_biomass,
    horizon=30,
    pine_revenue=12,           # $/m³
    eucalyptus_revenue=10,     # $/m³
    min_ending_biomass=25000,  # m³ - minimum biomass at end of horizon
    discount_rate=0.08         # 8% annual discount rate
)
```

---

### Step 4: Solve Optimization Model

```python
# Solve model with CBC solver
results = tm.solve_model(
    model, 
    solver_name='cbc',   # Free solver (included with treemun[solvers])
    gap=0.01,            # 1% optimality gap
    tee=False            # Set True to see solver output
)
```

**Alternative solvers:**
- `'cbc'` - Free, open-source (recommended)
- `'cplex'` - Commercial, requires license
- `'gurobi'` - Commercial, requires license

---

### Step 5: Extract Optimization Results

```python
# Extract optimal solution
solution = tm.extract_results(model, results)

# Solution contains:
# - objective_value: Net Present Value ($)
# - pinus_stand_plan: [(stand_id, policy_name), ...]
# - eucalyptus_stand_plan: [(stand_id, policy_name), ...]
# - total_harvest_per_period: [volume_t1, volume_t2, ...]

print(f"Optimal NPV: ${solution['objective_value']:,.2f}")
print(f"Pinus stands managed: {solution['total_pinus_stand_treated']}")
print(f"Eucalyptus stands managed: {solution['total_eucalyptus_stand_treated']}")
```

---

### Step 6: Export Optimal Policy to Shapefile

Export shapefile with **only the optimal policy** selected for each stand:

```python
# Export optimal management policy
gdf_opt = tm.export_optimal_policy_to_shapefile(
    forest=forest,
    summary=summary,
    shapefile_input="path_to_your_file/landscape.shp",
    shapefile_output="path_to_your_file/landscape_optimal.shp",
    solution=solution
)
```

**Generated attributes:**
```
id_rodal    - Stand ID
geometry    - Polygon geometry
pol_select  - Selected policy number (1, 2, 3, ...)
opt_policy  - Policy name (pol_pino1, pol_pino2, pol_euca1, pol_euca2, ...)
especie     - Species (Pinus or Eucapyltus)
bio_fin     - Final projected biomass (m³)
edad_fin    - Final stand age (years)
```

**Example output:**
```
stand1:  pol_select=2, opt_policy='pol_euca2', bio_fin=380.5, edad_fin=12
stand76: pol_select=1, opt_policy='pol_pino1', bio_fin=450.2, edad_fin=20
```

**Use this for:**
- Final management decision visualization
- Clean maps for presentations
- Communicating results to stakeholders
- Implementation planning

---

## Function Reference

### `export_simulation_to_shapefile()`

Exports complete simulation results with biomass attributes for all policies and periods.

**Signature:**
```python
export_simulation_to_shapefile(
    forest,              # List of DataFrames from simular_bosque()
    summary,             # Summary from simular_bosque()
    shapefile_input,     # Path to input shapefile
    shapefile_output     # Path for output shapefile
) -> GeoDataFrame
```

**Parameters:**
- `forest` - List of DataFrames from `simular_bosque()`
- `summary` - Summary from `simular_bosque()`
- `shapefile_input` - Path to input shapefile with geometries
- `shapefile_output` - Path for output enriched shapefile

**Returns:** `GeoDataFrame` with enriched attributes

**Raises:**
- `FileNotFoundError` - If input shapefile doesn't exist
- `ValueError` - If stand IDs don't match between simulation and shapefile

---

### `export_optimal_policy_to_shapefile()`

Exports shapefile with optimal policy selection for each stand.

**Signature:**
```python
export_optimal_policy_to_shapefile(
    forest,              # List of DataFrames from simular_bosque()
    summary,             # Summary from simular_bosque()
    shapefile_input,     # Path to input shapefile
    shapefile_output,    # Path for output shapefile
    solution             # Solution from extract_results() (optional)
) -> GeoDataFrame
```

**Parameters:**
- `forest` - List of DataFrames from `simular_bosque()`
- `summary` - Summary from `simular_bosque()`
- `shapefile_input` - Path to input shapefile
- `shapefile_output` - Path for output shapefile
- `solution` - Solution dict from `extract_results()` (optional)

**Returns:** `GeoDataFrame` with optimal policy attributes

**Note:** If `solution` is not provided, exports first policy of each stand.

---

## Output Format

### Attribute Naming Convention

**Simulation exports:** `bio_P[N]_t[T]`
- `bio` - Biomass prefix
- `P[N]` - Policy number (1, 2, 3, ...)
- `t[T]` - Time period (1, 2, ..., horizon)

**Examples:**
- `bio_P1_t1` = Biomass of policy 1 at period 1
- `bio_P1_t10` = Biomasa of policy 1 at period 10
- `bio_P2_t5` = Biomass of policy 2 at period 5

**Optimal policy exports:** `pol_[species][N]`
- `pol_pino1` = Pinus policy 1
- `pol_pino2` = Pinus policy 2
- `pol_euca1` = Eucalyptus policy 1
- `pol_euca2` = Eucalyptus policy 2
- `pol_euca3` = Eucalyptus policy 3

---

## QGIS Visualization

### Loading Shapefiles in QGIS

1. **Open QGIS**
2. **Layer** → **Add Layer** → **Add Vector Layer**
3. Select your `.shp` file
4. Click **Add**

### Visualization Options

#### Option 1: Categorize by Optimal Policy

For `landscape_optimal.shp`:

1. Right-click layer → **Properties** → **Symbology**
2. Select **Categorized**
3. Value: `opt_policy`
4. Click **Classify**
5. Assign colors:
   - `pol_pino1` → Dark green
   - `pol_pino2` → Medium green
   - `pol_pino3` → Light green
   - `pol_euca1` → Dark blue
   - `pol_euca2` → Medium blue
   - `pol_euca3` → Light blue

#### Option 2: Graduated by Final Biomass

1. Symbology → **Graduated**
2. Value: `bio_fin`
3. Color ramp: Yellow to Red
4. Mode: Natural Breaks (Jenks)
5. Classes: 5-7

#### Option 3: Filter by Species or Policy

**Show only Pinus stands:**
```sql
"opt_policy" LIKE 'pol_pino%'
```

**Show only Eucalyptus stands:**
```sql
"opt_policy" LIKE 'pol_euca%'
```

**Show specific policy number:**
```sql
"pol_select" = 2
```

**Show high-biomass stands:**
```sql
"bio_fin" > 400
```

---

## Troubleshooting

### Error: "No se pudo cargar el shapefile"

**Cause:** Shapefile path is incorrect or file doesn't exist.

**Solution:**
1. Verify file path is correct
2. Check all shapefile components exist (.shp, .shx, .dbf, .prj)
3. Use absolute paths to avoid confusion

---

### Error: "Rodales sin geometría en shapefile"

**Cause:** Stand IDs in CSV don't match IDs in shapefile.

**Solution:**
1. Check CSV file has correct `id_rodal` values (stand1, stand2, etc.)
2. Verify shapefile has matching IDs in `id_rodal` field
3. Ensure no typos (IDs are case-sensitive: "Stand1" ≠ "stand1")
4. Open shapefile in QGIS to verify ID field name and values

---

### Error: "Funciones espaciales no disponibles"

**Cause:** GeoPandas not installed.

**Solution:**
```bash
pip install treemun-sim[spatial]
```

---

### Warning: "El shapefile tiene [N] campos, que excede el límite de 254"

**Cause:** Too many attributes for shapefile format (long horizon + many policies).

**Solutions:**

**Option 1:** Reduce simulation horizon
```python
forest, summary, fb, cb = tm.simular_bosque(
    archivo_rodales="stands.csv",
    horizonte=20  # e.g.: Reduce from 30 to 20
)
```

**Option 2:** Export to GeoPackage (no field limit)
```python
gdf_sim.to_file("output.gpkg", driver="GPKG")
```

**Option 3:** Reduce number of policies
```python
forest, summary, fb, cb = tm.simular_bosque(
    archivo_rodales="stands.csv",
    policies_pino=[(10, 20), (11, 22)],      # Only 2 instead of 3
    policies_eucalyptus=[(10,), (11,)]       # Only 2 instead of 4
)
```

---

### Cannot use spatial analysis with random forests

**Issue:** Trying to use spatial functions with `num_rodales` parameter.

**Explanation:** Randomly generated stands (using `num_rodales`) don't have associated geometries, so spatial analysis is not possible.

**Solution:** Load stands from CSV file using `archivo_rodales` parameter and provide a shapefile with geometries.

---

## Complete Example

```python
import treemun_sim as tm

# ============================================================================
# STEP 1: Simulate forest growth (USER-PROVIDED STANDS ONLY)
# ============================================================================
forest, summary, final_biomass, collected_biomass = tm.simular_bosque(
    archivo_rodales="data/forest_stands.csv",  # NOT num_rodales!
    horizonte=10,
    policies_pino=[(10, 20), (11, 22), (12, 24)],
    policies_eucalyptus=[(9,), (10,), (11,), (12,)]
)

print(f"✓ Simulated {len(set([s['id_rodal'].iloc[0] for s in forest]))} stands")

# ============================================================================
# STEP 2: Export all simulations to shapefile
# ============================================================================
gdf_sim = tm.export_simulation_to_shapefile(
    forest=forest,
    summary=summary,
    shapefile_input="data/landscape.shp",
    shapefile_output="results/landscape_simulated.shp"
)

print(f"✓ Exported simulation shapefile: {len(gdf_sim.columns)} attributes")

# ============================================================================
# STEP 3: Optimize forest management
# ============================================================================
model = tm.forest_management_optimization_model(
    bosque=forest,
    a_i_j_T=final_biomass,
    a_i_j_t=collected_biomass,
    horizon=10,
    pine_revenue=12,
    eucalyptus_revenue=10,
    min_ending_biomass=25000,
    discount_rate=0.08
)

results = tm.solve_model(model, solver_name='cbc', gap=0.01)
solution = tm.extract_results(model, results)

print(f"✓ Optimal NPV: ${solution['objective_value']:,.2f}")

# ============================================================================
# STEP 4: Export optimal policy to shapefile
# ============================================================================
gdf_opt = tm.export_optimal_policy_to_shapefile(
    forest=forest,
    summary=summary,
    shapefile_input="data/landscape.shp",
    shapefile_output="results/landscape_optimal.shp",
    solution=solution
)

print(f"✓ Exported optimal policy shapefile")
print(f"  - Pinus stands: {solution['total_pinus_stand_treated']}")
print(f"  - Eucalyptus stands: {solution['total_eucalyptus_stand_treated']}")

# ============================================================================
# DONE! Open shapefiles in QGIS for visualization
# ============================================================================
```

---

## Best Practices

### 1. **Always Use User-Provided Stands**
Spatial analysis **only works** with `archivo_rodales` argument. Random generation (`num_rodales`) has no geometries.

### 2. **ID Matching is Critical**
Ensure `id_rodal` in CSV exactly matches field in shapefile. Use consistent naming (e.g., "stand1", "stand2", not "Stand1", "STAND1").

### 3. **Coordinate Systems**
Use projected coordinate systems (e.g., UTM) for accurate area calculations. Avoid geographic coordinates (lat/lon) for area-based analysis.

### 4. **Manage Field Limits**
Shapefiles have a 254 field limit. For long horizons (>30 years) with many policies:
- Reduce number of policies
- Shorten horizon
- Export to GeoPackage (.gpkg) instead

### 5. **Backup Original Files**
Always keep copies of original shapefiles and CSV files before running analysis.

### 6. **Verify Before Optimization**
Check that simulation shapefile looks correct in QGIS before running optimization. This catches ID mismatch issues early.

---

## Additional Resources

- **treemun-sim documentation:** https://github.com/fulloaf/treemun
- **GeoPandas documentation:** https://geopandas.org
- **QGIS tutorials:** https://qgis.org/en/docs/
- **Shapefile specification:** https://www.esri.com/content/dam/esrisites/sitecore-archive/Files/Pdfs/library/whitepapers/pdfs/shapefile.pdf

---

## Citation

If you use treemun-sim spatial simulation in your research, please cite:

```
Ulloa-Fierro, F. (2025). treemun-sim: Spatial forest growth simulation + optimization for forest planning. Version 1.2.0.
https://github.com/fulloaf/treemun
```

---

**Version:** 1.2.0  
**Last Updated:** 2025-02-12  
**Author:** Felipe Ulloa-Fierro

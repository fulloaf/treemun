# Input data

Treemün needs up to three inputs:

1. a **stand table** (required): what is on the ground today;
2. a **lookup table** of growth equations (bundled, replaceable);
3. **stand geometries** (optional): polygons for adjacency constraints and maps.

Management policies are the fourth ingredient and are passed as arguments to [`simulate_forest`](simulation.md#policies).

## Stand table

A CSV (or tab-delimited text) file with one row per stand and these columns:

| Column | Type | Example | Meaning |
|---|---|---|---|
| `stand_id` | text | `stand65` | unique identifier; also the join key to geometries |
| `area_ha` | number > 0 | `95.869` | stand area in hectares |
| `species` | text | `Pinus radiata` | `Pinus radiata` or `Eucalyptus globulus` |
| `initial_age` | integer ≥ 1 | `14` | biological age at the start of the horizon (years) |
| `zone` | integer | `6` | growth zone of the source tables |
| `site_index` | integer | `32` | dominant height (m) at reference age 10 |
| `management_regime` | text | `intensive_1` | see below |
| `growth_curve` | text | `pre_thinning_1250_700` | see below |
| `initial_density_trees_ha` | integer | `1250` | planting density (trees ha⁻¹) |

Valid combinations for the bundled lookup table:

| | *Pinus radiata* | *Eucalyptus globulus* |
|---|---|---|
| `zone` | 6, 7 | 1, 2 |
| `site_index` | 26 (multipurpose), 29 (intensive_2), 32 (intensive_1) | 24, 26, 28, 30, 32 |
| `management_regime` | `multipurpose`, `intensive_1`, `intensive_2` | `none` |
| `growth_curve` | `pre_thinning_1250_700` | `unthinned` |
| `initial_density_trees_ha` | 1250 | 800, 1250 |

!!! note "Pine stands always start before thinning"
    In Treemün 2.0.0 every pine stand must start on a pre-thinning curve whose `next_equation_id` links to a post-thinning curve. The post-thinning state is reached only through a thinning simulated inside the horizon. The two unthinned `pulpwood` pine equations are distributed in the lookup table but are rejected as initial conditions.

Example (first rows of `examples/forest_stands.csv`):

```text
stand_id,area_ha,species,initial_age,zone,site_index,management_regime,growth_curve,initial_density_trees_ha
stand65,95.869,Pinus radiata,14,6,32,intensive_1,pre_thinning_1250_700,1250
stand68,86.208,Pinus radiata,12,7,32,intensive_1,pre_thinning_1250_700,1250
stand75,73.302,Pinus radiata,10,6,29,intensive_2,pre_thinning_1250_700,1250
```

### Validation

`load_stand_table` (called automatically by `simulate_forest`) stops with a descriptive error instead of guessing when:

- a required column is missing, a `stand_id` is empty or duplicated;
- `area_ha` is not positive, or `initial_age` is below 1;
- a numeric field cannot be parsed;
- a stand does not match exactly one equation in the lookup table;
- a pine stand does not start on a pre-thinning curve with a valid post-thinning link.

No value is ever imputed, because an imputed biomass would propagate silently into every downstream coefficient.

### Files from Treemün 1.x

Spanish column names (`id_rodal`, `hectareas`, `especie`, …) and the old curve labels are converted automatically, with a deprecation warning. To convert a file permanently:

```python
import treemun_sim as tm
tm.convert_v1_stand_file("stands_v1.csv", "stands_v2.csv")
```

See [Migration from 1.x](../reference/migration.md).

## Lookup table

The bundled table (`treemun_sim/data/lookup_table.csv`, 34 rows) holds one growth equation per row:

| Column | Meaning |
|---|---|
| `equation_id` | unique identifier |
| `next_equation_id` | for pine pre-thinning curves, the post-thinning equation used after thinning |
| `species`, `zone`, `initial_density_trees_ha`, `site_index`, `management_regime`, `growth_curve` | stratum keys matched against the stand table |
| `alpha`, `beta`, `gamma` | coefficients of the surrogate function |

Each equation gives dry aboveground biomass (Mg ha⁻¹) as a function of biological age \(e\):

\[
b(e) = \max\left\{\alpha\, e^{\beta} + \gamma,\ 0\right\}
\]

```python
lookup = tm.load_lookup_table()
lookup.groupby(["species", "growth_curve"]).size()
```

```text
species              growth_curve
Eucalyptus globulus  unthinned                20
Pinus radiata        post_thinning_700_300     6
                     pre_thinning_1250_700     6
                     unthinned                 2
```

To use other species, strata or recalibrated coefficients, write a table with the same columns and pass it to `simulate_forest(..., lookup_table_file="my_lookup.csv")`. The coefficients are listed in [Growth models](../reference/growth-models.md).

## Stand geometries

Needed only for [spatial planning](spatial.md) and [GIS export](gis-export.md).

- GeoPackage (preferred) or Shapefile;
- one polygon per `stand_id`, with the same identifiers as the stand table;
- a **projected** coordinate reference system (metres), because shared-boundary lengths are measured in map units.

The example file `examples/treemun_landscape.gpkg` has a `stands` layer with 105 polygons in UTM zone 18S (EPSG:32718).

!!! tip
    Prefer GeoPackage: Shapefile truncates field names to 10 characters, which mangles names such as `standing_dry_wood_t_after_operation`.

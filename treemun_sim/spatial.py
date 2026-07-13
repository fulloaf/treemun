# -*- coding: utf-8 -*-

#treemun/treemun_sim/spatial.py

"""
Módulo Spatial para treemun-sim
================================

Funciones para integración espacial de resultados de simulación forestal
con shapefiles.

Este módulo permite:
- Exportar resultados de simulación a shapefiles con atributos de biomasa
- Exportar soluciones óptimas a shapefiles

"""

import geopandas as gpd
import pandas as pd
from typing import List, Dict, Optional
import warnings
import re
from pathlib import Path



def _extract_policy_number(policy_str: str) -> int:
    """
    Extrae el número de política de un string.

    Examples
    --------
    'policy_pino 1' -> 1
    'policy_eucalyptus 3' -> 3
    """
    match = re.search(r'(\d+)$', str(policy_str))
    if match:
        return int(match.group(1))
    return 1


def solution_to_selected_policies(solution: Dict) -> pd.DataFrame:
    """
    Convierte el output de extract_results() a un DataFrame con las políticas
    seleccionadas por rodal.

    A diferencia de la versión anterior, esta función conserva:
        - species
        - stand id
        - full policy name
        - policy number

    Returns
    -------
    pd.DataFrame
        Columns:
            id_rodal, especie, policy, policy_num, x_ij
    """
    records = []

    if solution is None:
        return pd.DataFrame(
            columns=["id_rodal", "especie", "policy", "policy_num", "x_ij"]
        )

    for stand_id, policy_name in solution.get("pinus_stand_plan", []):
        records.append(
            {
                "id_rodal": stand_id,
                "especie": "Pinus",
                "policy": policy_name,
                "policy_num": _extract_policy_number(policy_name),
                "x_ij": 1,
            }
        )

    for stand_id, policy_name in solution.get("eucalyptus_stand_plan", []):
        records.append(
            {
                "id_rodal": stand_id,
                "especie": "Eucalyptus",
                "policy": policy_name,
                "policy_num": _extract_policy_number(policy_name),
                "x_ij": 1,
            }
        )

    selected_df = pd.DataFrame(records)

    if selected_df.empty:
        return pd.DataFrame(
            columns=["id_rodal", "especie", "policy", "policy_num", "x_ij"]
        )

    selected_df["id_rodal"] = selected_df["id_rodal"].astype(str)
    selected_df["policy"] = selected_df["policy"].astype(str)

    return selected_df


def _summary_to_policy_catalog(summary: List[Dict]) -> pd.DataFrame:
    """
    Convierte summary/resumen_c a un catálogo rodal-política.

    summary no es la solución óptima; es el catálogo de políticas simuladas
    para cada rodal.
    """
    if summary is None:
        return pd.DataFrame()

    catalog = pd.DataFrame(summary)

    if catalog.empty:
        return catalog

    rename_map = {
        "id_rodal": "id_rodal",
        "especie": "especie",
        "has": "has",
        "edad_inicial": "edad_ini",
        "edad_final": "edad_fin_cat",
        "policy": "policy",
        "ecuacion_inicial_id": "eq_ini_id",
    }

    keep = [c for c in rename_map if c in catalog.columns]
    catalog = catalog[keep].rename(columns=rename_map)

    if "id_rodal" in catalog.columns:
        catalog["id_rodal"] = catalog["id_rodal"].astype(str)

    if "policy" in catalog.columns:
        catalog["policy"] = catalog["policy"].astype(str)
        catalog["policy_num"] = catalog["policy"].apply(_extract_policy_number)

    return catalog.drop_duplicates()


def _forest_to_policy_outputs(forest: List[pd.DataFrame]) -> pd.DataFrame:
    """
    Extrae atributos finales de cada trayectoria simulada en forest.

    Se usa para recuperar biomasa final, edad final y, si existen, atributos
    de carbono asociados a la política seleccionada.
    """
    records = []

    for df in forest:
        if df is None or df.empty:
            continue

        stand_id = df["id_rodal"].iloc[0]

        if "Especie" in df.columns:
            especie = df["Especie"].iloc[0]
        elif "especie" in df.columns:
            especie = df["especie"].iloc[0]
        else:
            especie = None

        if "politica" in df.columns:
            policy = df["politica"].iloc[0]
        elif "policy" in df.columns:
            policy = df["policy"].iloc[0]
        else:
            policy = None

        policy_num = _extract_policy_number(policy)

        last = df.iloc[-1]

        rec = {
            "id_rodal": str(stand_id),
            "especie": especie,
            "policy": str(policy),
            "policy_num": policy_num,
            "bio_fin": round(float(last["biomasa"]), 2) if "biomasa" in df.columns else None,
            "edad_fin": int(last["edad_rodal"]) if "edad_rodal" in df.columns else None,
        }

        # Optional carbon-related columns if forest was simulated with Carbon=True.
        optional_cols = {
            "CarbonStockPost_MgC": "cpost_mgc",
            "RemovedCarbon_MgC": "crem_mgc",
            "CarbSeq_MgC": "cseq_mgc",
            "CarbSeqOPT": "cseq_opt",
            "CarbEqvOPT": "ceqv_opt",
        }

        for source_col, out_col in optional_cols.items():
            if source_col in df.columns:
                try:
                    rec[out_col] = float(last[source_col])
                except Exception:
                    rec[out_col] = None

        records.append(rec)

    out = pd.DataFrame(records)

    if out.empty:
        return out

    out["id_rodal"] = out["id_rodal"].astype(str)
    out["policy"] = out["policy"].astype(str)

    return out.drop_duplicates()




def export_simulation_to_shapefile(
    forest: List[pd.DataFrame],
    summary: List[Dict],
    shapefile_input: str,
    shapefile_output: str
) -> gpd.GeoDataFrame:
    """
    Exporta resultados de simulación forestal a shapefile con atributos de biomasa.
    
    Para cada rodal y cada política simulada, se agregan atributos de biomasa
    por periodo en el formato: bio_P[N]_t[T] donde N es el número de política
    y T es el periodo.
    
    Args:
        forest: Lista de DataFrames con simulaciones (salida de simular_bosque)
        summary: Resumen de simulaciones
        shapefile_input: Ruta al shapefile original con geometrías
        shapefile_output: Ruta donde guardar shapefile enriquecido
    
    Returns:
        GeoDataFrame con todos los atributos agregados
    
    Example:
        >>> import treemun_sim as tm
        >>> forest, summary, fb, cb = tm.simular_bosque(
        ...     archivo_rodales="bosque.csv",
        ...     horizonte=30
        ... )
        >>> gdf = tm.export_simulation_to_shapefile(
        ...     forest=forest,
        ...     summary=summary,
        ...     shapefile_input="bosque.shp",
        ...     shapefile_output="bosque_simulado.shp"
        ... )
    """
    
    # Configuración fija interna
    campo_id = 'id_rodal'
    prefix_biomass = 'bio'
    include_static_attributes = True
    max_periods = None  # Exportar todos los periodos
    
    # 1. Validar y cargar shapefile
    try:
        gdf = gpd.read_file(shapefile_input)
    except Exception as e:
        raise FileNotFoundError(f"No se pudo cargar el shapefile: {shapefile_input}. Error: {e}")
    
    # 2. Validar que existe campo_id
    if campo_id not in gdf.columns:
        raise ValueError(
            f"Campo '{campo_id}' no encontrado en shapefile. "
            f"Columnas disponibles: {list(gdf.columns)}"
        )
    
    # 3. Extraer IDs únicos de forest
    ids_forest = set([df['id_rodal'].iloc[0] for df in forest])
    ids_shapefile = set(gdf[campo_id].values)
    
    # 4. Validar coincidencias
    ids_sin_geometria = ids_forest - ids_shapefile
    ids_sin_datos = ids_shapefile - ids_forest
    
    if ids_sin_geometria:
        raise ValueError(
            f"Rodales sin geometría en shapefile: {sorted(ids_sin_geometria)}\n"
            f"Estos rodales están en la simulación pero no tienen geometría."
        )
    
    if ids_sin_datos:
        warnings.warn(
            f"Geometrías sin datos de simulación: {sorted(ids_sin_datos)}\n"
            f"Estas geometrías están en el shapefile pero no fueron simuladas.",
            UserWarning
        )
    
    # 5. Crear diccionario de atributos por rodal
    attributes_dict = {}
    
    print(f"Exportando simulaciones a shapefile...")
    print(f"  Rodales en forest: {len(ids_forest)}")
    print(f"  Rodales en shapefile: {len(ids_shapefile)}")
    
    # Crear diccionario auxiliar con info de summary (para hectáreas)
    summary_dict = {}
    for item in summary:
        stand_id = item['id_rodal']
        if stand_id not in summary_dict:
            summary_dict[stand_id] = {
                'hectareas': item.get('has', 0),
                'especie': item['especie']
            }
    
    for stand_df in forest:
        stand_id = stand_df['id_rodal'].iloc[0]
        especie = stand_df['Especie'].iloc[0]
        politica_str = stand_df['politica'].iloc[0]
        
        # Extraer solo el número de la política
        politica_num = _extract_policy_number(politica_str)
        
        if stand_id not in attributes_dict:
            attributes_dict[stand_id] = {}
            
            # Agregar atributos estáticos
            if include_static_attributes:
                attributes_dict[stand_id]['especie'] = especie
                if stand_id in summary_dict:
                    attributes_dict[stand_id]['hectareas'] = round(summary_dict[stand_id]['hectareas'], 2)
                attributes_dict[stand_id]['edad_ini'] = int(stand_df['edad_rodal'].iloc[0])
        
        # Determinar cuántos periodos exportar
        periodos = stand_df['periodo'].values
        if max_periods is not None:
            periodos = periodos[:max_periods]
        
        # Agregar biomasa por periodo
        for periodo in periodos:
            row = stand_df[stand_df['periodo'] == periodo]
            if len(row) > 0:
                biomasa = row['biomasa'].iloc[0]
                
                # Formato: bio_P[N]_t[T]
                attr_name = f"{prefix_biomass}_P{politica_num}_t{periodo}"
                attributes_dict[stand_id][attr_name] = round(biomasa, 2)
    
    # 6. Convertir diccionario a DataFrame
    attrs_df = pd.DataFrame.from_dict(attributes_dict, orient='index')
    attrs_df.index.name = campo_id
    attrs_df.reset_index(inplace=True)
    
    # 7. Hacer merge con GeoDataFrame
    gdf_enriched = gdf.merge(attrs_df, on=campo_id, how='left')
    
    # 8. Advertir sobre límite de campos
    n_campos = len(gdf_enriched.columns)
    if n_campos > 254:
        warnings.warn(
            f"El shapefile tiene {n_campos} campos, que excede el límite de 254 "
            f"para archivos .shp. Considera reducir el horizonte de simulación "
            f"o exportar a otro formato como GeoPackage (.gpkg).",
            UserWarning
        )
    
    # 9. Guardar shapefile enriquecido
    try:
        gdf_enriched.to_file(shapefile_output)
    except Exception as e:
        raise IOError(f"Error al guardar shapefile: {shapefile_output}. Error: {e}")
    
    # 10. Resumen
    n_atributos_nuevos = len(gdf_enriched.columns) - len(gdf.columns)
    
    print(f"\n✓ Shapefile exportado: {shapefile_output}")
    print(f"  - Rodales totales: {len(gdf_enriched)}")
    print(f"  - Atributos totales: {len(gdf_enriched.columns)}")
    print(f"  - Atributos nuevos agregados: {n_atributos_nuevos}")
    
    return gdf_enriched


def export_optimal_policy_to_shapefile(
    forest: List[pd.DataFrame],
    summary: List[Dict],
    shapefile_input: str,
    shapefile_output: str,
    solution: Optional[Dict] = None,
    campo_id: str = "id_rodal",
    biom_simu: bool = False,
    carbseqSim: bool = False,
    max_periods: Optional[int] = None,
    round_digits: int = 2,
    allow_first_policy_fallback: bool = False,
) -> gpd.GeoDataFrame:
    """
    Exporta una solución óptima puntual a un archivo espacial.

    Por defecto, la función genera un nuevo archivo espacial que conserva todos
    los atributos originales del shapefile y agrega únicamente:

        opt_policy

    donde opt_policy corresponde a la política seleccionada por el modelo de
    optimización para cada rodal.

    Opcionalmente, puede agregar las trayectorias simuladas asociadas a la
    política óptima seleccionada:

    - Si biom_simu=True:
        agrega biomasa simulada por período con nombres como:
            bio_P1_t1, bio_P1_t2, ..., bio_P1_t10

    - Si carbseqSim=True:
        agrega CarbSeq_MgC por período con nombres como:
            CSeqP1_t1, CSeqP1_t2, ..., CSeqP1_t10

    Parameters
    ----------
    forest : list[pandas.DataFrame]
        Lista de DataFrames generada por simular_bosque(). Cada DataFrame
        corresponde a una trayectoria rodal-política.

    summary : list[dict]
        Catálogo de políticas simuladas generado por simular_bosque().
        Se mantiene como argumento por compatibilidad, pero la política óptima
        se obtiene desde solution.

    shapefile_input : str
        Ruta del shapefile/archivo espacial original.

    shapefile_output : str
        Ruta del archivo espacial de salida. Puede ser .shp o .gpkg.

    solution : dict
        Output de extract_results(). Debe contener:
            pinus_stand_plan
            eucalyptus_stand_plan

    campo_id : str
        Nombre del campo identificador del rodal en el archivo espacial.

    biom_simu : bool
        Si True, exporta la biomasa simulada por período para la política óptima.

    carbseqSim : bool
        Si True, exporta CarbSeq_MgC por período para la política óptima.

    max_periods : int or None
        Número máximo de períodos a exportar. Si None, exporta todos los períodos
        disponibles en forest.

    round_digits : int
        Número de decimales para atributos numéricos exportados.

    allow_first_policy_fallback : bool
        Si True y solution=None, exporta la primera política disponible por rodal.
        Por defecto es False para evitar confundir una política de referencia
        con una política óptima.

    Returns
    -------
    geopandas.GeoDataFrame
        GeoDataFrame con atributos originales más opt_policy y, opcionalmente,
        biomasa/carbono por período.
    """

    def _get_policy_number(policy_name):
        return _extract_policy_number(policy_name)

    def _get_policy_col(df):
        if "politica" in df.columns:
            return "politica"
        if "policy" in df.columns:
            return "policy"
        raise ValueError(
            "No se encontró columna de política en un DataFrame de forest. "
            "Se esperaba 'politica' o 'policy'."
        )

    def _get_period_col(df):
        if "periodo" in df.columns:
            return "periodo"
        if "period" in df.columns:
            return "period"
        raise ValueError(
            "No se encontró columna de período en un DataFrame de forest. "
            "Se esperaba 'periodo' o 'period'."
        )

    def _solution_to_selected_df(solution):
        records = []

        if solution is None:
            return pd.DataFrame(columns=["id_rodal", "opt_policy"])

        for stand_id, policy_name in solution.get("pinus_stand_plan", []):
            records.append(
                {
                    "id_rodal": str(stand_id),
                    "opt_policy": str(policy_name),
                }
            )

        for stand_id, policy_name in solution.get("eucalyptus_stand_plan", []):
            records.append(
                {
                    "id_rodal": str(stand_id),
                    "opt_policy": str(policy_name),
                }
            )

        return pd.DataFrame(records).drop_duplicates()

    def _fallback_first_policy_from_summary(summary):
        if summary is None:
            return pd.DataFrame(columns=["id_rodal", "opt_policy"])

        df = pd.DataFrame(summary)

        if df.empty:
            return pd.DataFrame(columns=["id_rodal", "opt_policy"])

        if "id_rodal" not in df.columns or "policy" not in df.columns:
            raise ValueError(
                "summary debe contener columnas 'id_rodal' y 'policy' para "
                "usar allow_first_policy_fallback=True."
            )

        df = df.copy()
        df["policy_num"] = df["policy"].apply(_extract_policy_number)

        selected = (
            df.sort_values(["id_rodal", "policy_num"])
            .groupby("id_rodal", as_index=False)
            .first()[["id_rodal", "policy"]]
            .rename(columns={"policy": "opt_policy"})
        )

        selected["id_rodal"] = selected["id_rodal"].astype(str)
        selected["opt_policy"] = selected["opt_policy"].astype(str)

        return selected

    def _find_selected_trajectory(forest, stand_id, opt_policy):
        """
        Busca en forest el DataFrame que corresponde al rodal y política óptima.
        Primero intenta coincidencia exacta por nombre de política.
        Si falla, usa el número de política como respaldo.
        """
        stand_id = str(stand_id)
        opt_policy = str(opt_policy)
        opt_policy_num = _get_policy_number(opt_policy)

        candidates_same_stand = []

        for df in forest:
            if df is None or df.empty:
                continue

            if "id_rodal" not in df.columns:
                continue

            df_stand = str(df["id_rodal"].iloc[0])

            if df_stand != stand_id:
                continue

            candidates_same_stand.append(df)

            policy_col = _get_policy_col(df)
            df_policy = str(df[policy_col].iloc[0])

            if df_policy == opt_policy:
                return df

        # Fallback por número de política dentro del mismo rodal.
        for df in candidates_same_stand:
            policy_col = _get_policy_col(df)
            df_policy = str(df[policy_col].iloc[0])

            if _get_policy_number(df_policy) == opt_policy_num:
                return df

        return None

    # ------------------------------------------------------------------
    # 1. Load spatial file
    # ------------------------------------------------------------------
    try:
        gdf = gpd.read_file(shapefile_input)
    except Exception as e:
        raise FileNotFoundError(
            f"No se pudo cargar el archivo espacial: {shapefile_input}. Error: {e}"
        )

    if campo_id not in gdf.columns:
        raise ValueError(
            f"Campo '{campo_id}' no encontrado en archivo espacial. "
            f"Columnas disponibles: {list(gdf.columns)}"
        )

    gdf[campo_id] = gdf[campo_id].astype(str)

    # ------------------------------------------------------------------
    # 2. Build selected policy table
    # ------------------------------------------------------------------
    selected_df = _solution_to_selected_df(solution)

    if selected_df.empty:
        if not allow_first_policy_fallback:
            raise ValueError(
                "solution no contiene políticas seleccionadas. "
                "Debes pasar solution=tm.extract_results(model, results). "
                "Si quieres exportar la primera política disponible por rodal, "
                "usa allow_first_policy_fallback=True."
            )

        warnings.warn(
            "No se entregó una solución óptima. Se exportará la primera política "
            "disponible por rodal como referencia.",
            UserWarning,
        )

        selected_df = _fallback_first_policy_from_summary(summary)

    if selected_df.empty:
        raise ValueError("No se pudo construir la tabla de políticas seleccionadas.")

    selected_df["id_rodal"] = selected_df["id_rodal"].astype(str)
    selected_df["opt_policy"] = selected_df["opt_policy"].astype(str)

    # ------------------------------------------------------------------
    # 3. Build attributes by stand
    # ------------------------------------------------------------------
    attributes = {}

    for _, row in selected_df.iterrows():
        stand_id = row["id_rodal"]
        opt_policy = row["opt_policy"]
        policy_num = _get_policy_number(opt_policy)

        attributes[stand_id] = {
            "opt_policy": opt_policy,
        }

        if biom_simu or carbseqSim:
            traj = _find_selected_trajectory(
                forest=forest,
                stand_id=stand_id,
                opt_policy=opt_policy,
            )

            if traj is None:
                warnings.warn(
                    f"No se encontró trayectoria simulada para rodal={stand_id}, "
                    f"opt_policy={opt_policy}.",
                    UserWarning,
                )
                continue

            period_col = _get_period_col(traj)
            traj_sorted = traj.sort_values(period_col).copy()

            if max_periods is not None:
                traj_sorted = traj_sorted.head(max_periods)

            for _, trow in traj_sorted.iterrows():
                period = int(trow[period_col])

                if biom_simu:
                    if "biomasa" not in traj_sorted.columns:
                        raise ValueError(
                            "biom_simu=True requiere que los DataFrames de forest "
                            "contengan la columna 'biomasa'."
                        )

                    attr_name = f"bio_P{policy_num}_t{period}"
                    attributes[stand_id][attr_name] = round(
                        float(trow["biomasa"]),
                        round_digits,
                    )

                if carbseqSim:
                    if "CarbSeq_MgC" not in traj_sorted.columns:
                        raise ValueError(
                            "carbseqSim=True requiere que los DataFrames de forest "
                            "contengan la columna 'CarbSeq_MgC'. "
                            "Asegúrate de correr simular_bosque(..., Carbon=True)."
                        )

                    attr_name = f"CSeqP{policy_num}_t{period}"
                    attributes[stand_id][attr_name] = round(
                        float(trow["CarbSeq_MgC"]),
                        round_digits,
                    )

    attrs_df = pd.DataFrame.from_dict(attributes, orient="index")
    attrs_df.index.name = campo_id
    attrs_df.reset_index(inplace=True)

    # ------------------------------------------------------------------
    # 4. Merge with original geometries
    # ------------------------------------------------------------------
    gdf_export = gdf.merge(
        attrs_df,
        on=campo_id,
        how="left",
    )

    # ------------------------------------------------------------------
    # 5. Warnings for shapefile format
    # ------------------------------------------------------------------
    if str(shapefile_output).lower().endswith(".shp"):
        long_cols = [c for c in gdf_export.columns if len(str(c)) > 10]

        if long_cols:
            warnings.warn(
                "El formato .shp limita los nombres de campos a 10 caracteres. "
                f"Campos potencialmente truncados: {long_cols}. "
                "Para conservar nombres completos, considera exportar a .gpkg.",
                UserWarning,
            )

        if len(gdf_export.columns) > 254:
            warnings.warn(
                f"El shapefile tendría {len(gdf_export.columns)} campos, lo que "
                "puede exceder el límite del formato .shp. Considera usar .gpkg.",
                UserWarning,
            )

    # ------------------------------------------------------------------
    # 6. Save output
    # ------------------------------------------------------------------
    try:
        output_path = Path(shapefile_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        gdf_export.to_file(shapefile_output)
    except Exception as e:
        raise IOError(
            f"Error al guardar archivo espacial: {shapefile_output}. Error: {e}"
        )

    print(f"\n✓ Solución óptima exportada: {shapefile_output}")
    print(f"  - Rodales en archivo espacial: {len(gdf_export)}")
    print(f"  - Rodales con opt_policy: {attrs_df[campo_id].nunique()}")
    print(f"  - biom_simu: {biom_simu}")
    print(f"  - carbseqSim: {carbseqSim}")

    return gdf_export


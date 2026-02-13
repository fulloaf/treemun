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


def _extract_policy_number(policy_str: str) -> int:
    """
    Extrae el número de política de un string.
    
    Args:
        policy_str: String como "policy_pino 1" o "policy_eucalyptus 2"
    
    Returns:
        Número de política como entero
    """
    match = re.search(r'(\d+)$', str(policy_str))
    if match:
        return int(match.group(1))
    return 1  # Default


def solution_to_selected_policies(solution: Dict) -> Dict[str, int]:
    """
    Convierte el formato de solution (output de extract_results) a un diccionario
    de políticas seleccionadas.
    
    Args:
        solution: Diccionario con claves 'pinus_stand_plan' y 'eucalyptus_stand_plan'
                 Cada uno es una lista de tuplas (stand_id, policy_name)
    
    Returns:
        Diccionario {stand_id: policy_number}
    
    Example:
        >>> solution = {
        ...     'pinus_stand_plan': [('stand1', 'policy_pino 2'), ('stand3', 'policy_pino 1')],
        ...     'eucalyptus_stand_plan': [('stand2', 'policy_eucalyptus 3')]
        ... }
        >>> selected = solution_to_selected_policies(solution)
        >>> print(selected)
        # {'stand1': 2, 'stand3': 1, 'stand2': 3}
    """
    selected_policies = {}
    
    # Procesar Pinus
    if 'pinus_stand_plan' in solution:
        for stand_id, policy_name in solution['pinus_stand_plan']:
            policy_num = _extract_policy_number(policy_name)
            selected_policies[stand_id] = policy_num
    
    # Procesar Eucalyptus
    if 'eucalyptus_stand_plan' in solution:
        for stand_id, policy_name in solution['eucalyptus_stand_plan']:
            policy_num = _extract_policy_number(policy_name)
            selected_policies[stand_id] = policy_num
    
    return selected_policies


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
    solution: Optional[Dict] = None
) -> gpd.GeoDataFrame:
    """
    Exporta información de las políticas óptimas a shapefile.
    
    Si se proporciona `solution` (output de extract_results), exporta las políticas 
    óptimas seleccionadas por el optimizador. Si no, exporta la primera política de 
    cada rodal como referencia.
    
    Args:
        forest: Lista de DataFrames con simulaciones
        summary: Resumen de simulaciones  
        shapefile_input: Ruta al shapefile original
        shapefile_output: Ruta para shapefile con políticas
        solution: Dict output de extract_results() con políticas óptimas (opcional)
    
    Returns:
        GeoDataFrame con atributos de políticas
    
    Example:
        >>> # Con optimización (recomendado)
        >>> model = tm.forest_management_optimization_model(...)
        >>> results = tm.solve_model(model)
        >>> solution = tm.extract_results(model, results)
        >>> 
        >>> gdf_opt = tm.export_optimal_policy_to_shapefile(
        ...     forest=forest,
        ...     summary=summary,
        ...     shapefile_input="bosque.shp",
        ...     shapefile_output="bosque_optimo.shp",
        ...     solution=solution
        ... )
    """
    
    campo_id = 'id_rodal'
    
    # Cargar shapefile
    gdf = gpd.read_file(shapefile_input)
    
    if campo_id not in gdf.columns:
        raise ValueError(f"Campo '{campo_id}' no encontrado en shapefile")
    
    # Convertir solution a diccionario de políticas seleccionadas si se proporciona
    selected_policies = None
    if solution:
        selected_policies = solution_to_selected_policies(solution)
    
    # Crear diccionario de atributos por rodal
    stands_data = {}
    
    for df in forest:
        stand_id = df['id_rodal'].iloc[0]
        especie = df['Especie'].iloc[0]
        politica_str = df['politica'].iloc[0]
        
        # Extraer número de política
        policy_num = _extract_policy_number(politica_str)
        
        if stand_id not in stands_data:
            stands_data[stand_id] = {
                'especie': especie,
                'policies': {}
            }
        
        # Guardar info de esta política
        stands_data[stand_id]['policies'][policy_num] = {
            'biomasa_final': df['biomasa'].iloc[-1],
            'edad_final': df['edad_rodal'].iloc[-1]
        }
    
    # Crear atributos para cada rodal
    opt_attributes = {}
    
    for stand_id, data in stands_data.items():
        # Determinar qué política usar
        if selected_policies and stand_id in selected_policies:
            # Usar política seleccionada por optimizador
            policy_num = selected_policies[stand_id]
        else:
            # Usar la primera política disponible
            policy_num = min(data['policies'].keys())
        
        if policy_num in data['policies']:
            policy_data = data['policies'][policy_num]
            
            # Crear nombre de política según especie
            if data['especie'] == 'Pinus':
                policy_name = f'pol_pino{policy_num}'
            else:  # Eucapyltus
                policy_name = f'pol_euca{policy_num}'
            
            opt_attributes[stand_id] = {
                'pol_select': int(policy_num),
                'opt_policy': policy_name,
                'especie': data['especie'],
                'bio_fin': round(policy_data['biomasa_final'], 2),
                'edad_fin': int(policy_data['edad_final'])
            }
    
    # Convertir a DataFrame
    opt_df = pd.DataFrame.from_dict(opt_attributes, orient='index')
    opt_df.index.name = campo_id
    opt_df.reset_index(inplace=True)
    
    # Merge con geometrías
    gdf_optimal = gdf.merge(opt_df, on=campo_id, how='left')
    
    # Guardar
    gdf_optimal.to_file(shapefile_output)
    
    print(f"\n✓ Políticas exportadas: {shapefile_output}")
    print(f"  - Rodales con política: {len(opt_df)}")
    if selected_policies:
        print(f"  - Políticas óptimas del optimizador")
        if solution and 'objective_value' in solution:
            print(f"  - VPN total: ${solution['objective_value']:,.2f}")
    else:
        print(f"  - Primera política de cada rodal (sin optimización)")
    
    return gdf_optimal
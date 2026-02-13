#!/usr/bin/env python
# coding: utf-8

# In[ ]:


# treemun/generadores.py

"""
Módulo para generación de rodales aleatorios y aplicación de políticas de manejo.

"""

import numpy as np
import pandas as pd
import random
from typing import List, Tuple, Dict, Any
import os

# IDs válidos para pinos iniciales (del código original)
IDS_PINOS_INICIALES_VALIDOS = [21, 22, 25, 26, 29, 30]

def cargar_rodales_desde_archivo(
    archivo: str,
    df: pd.DataFrame,
    dict_idx: Dict,
    horizonte: int,
    policies_pino: List[Tuple[int, int]],
    policies_eucalyptus: List[Tuple[int,]]
) -> Dict[str, Any]:
    """
    Carga rodales desde un archivo CSV o TXT.
    
    Columnas requeridas en el archivo:
    - id_rodal: Identificador único del rodal (string)
    - hectareas: Superficie en hectáreas (float)
    - especie: 'Pinus' o 'Eucapyltus' (string)
    - edad_inicial: Edad inicial del rodal en años (int)
    - zona: Zona geográfica (string, ej: 'Z6', 'Z7', 'Z01', 'Z02')
    - site_index: Índice de sitio (int, ej: 23, 26, 29, 32 para Pinus; 24-32 para Eucalyptus)
    - manejo: Tipo de manejo (string, ej: 'Multipropósito', 'Intensivo', 'NA')
    - condicion: Condición del rodal (string, ej: 'con manejo', 'sin manejo', 'SinManejo')
    - densidad_inicial: Densidad inicial de árboles por ha (int, ej: 800, 1250)
    
    Args:
        archivo: Ruta al archivo CSV/TXT
        df: DataFrame con la lookup table
        dict_idx: Diccionario de índices de la lookup table
        horizonte: Horizonte temporal de la simulación
        policies_pino: Lista de políticas para pino
        policies_eucalyptus: Lista de políticas para eucalipto
        
    Returns:
        Diccionario de configuración compatible con generar_rodales()
        
    Raises:
        FileNotFoundError: Si el archivo no existe
        ValueError: Si faltan columnas requeridas o valores inválidos
    """
    
    # Verificar que el archivo existe
    if not os.path.exists(archivo):
        raise FileNotFoundError(f"No se encontró el archivo: {archivo}")
    
    # Determinar separador según extensión
    ext = os.path.splitext(archivo)[1].lower()
    if ext == '.csv':
        sep = ','
    elif ext == '.txt':
        sep = '\t'
    else:
        # Intentar detectar automáticamente
        sep = None
    
    # Cargar archivo
    try:
        if sep:
            rodales_df = pd.read_csv(archivo, sep=sep)
        else:
            rodales_df = pd.read_csv(archivo, sep=None, engine='python')
    except Exception as e:
        raise ValueError(f"Error al leer el archivo: {e}")
    
    # Columnas requeridas
    columnas_requeridas = [
        'id_rodal', 'hectareas', 'especie', 'edad_inicial', 
        'zona', 'site_index', 'manejo', 'condicion', 'densidad_inicial'
    ]
    
    # Verificar columnas
    columnas_faltantes = set(columnas_requeridas) - set(rodales_df.columns)
    if columnas_faltantes:
        raise ValueError(
            f"Faltan las siguientes columnas requeridas: {', '.join(columnas_faltantes)}\n"
            f"Columnas encontradas: {', '.join(rodales_df.columns)}"
        )
    
    print(f"Cargando {len(rodales_df)} rodales desde {archivo}...")
    
    # Listas para almacenar los datos validados
    edades_iniciales = []
    hectareas = []
    ids_rodales = []
    especies_aleatorias = []
    zonas_aleatorias = []
    site_indices_aleatorios = []
    densidades_iniciales_aleatorias = []
    manejos_aleatorios = []
    condiciones_aleatorias = []
    
    # Contadores
    pinos_count = 0
    eucas_count = 0
    rodales_invalidos = []
    
    # Procesar cada rodal
    for idx, row in rodales_df.iterrows():
        try:
            # Extraer valores
            id_rodal = str(row['id_rodal'])
            hectarea = float(row['hectareas'])
            especie_raw = str(row['especie']).strip()
            edad_inicial = int(row['edad_inicial'])
            zona = int(row['zona'])
            site_index = int(row['site_index'])
            manejo_raw = row['manejo']
            condicion = str(row['condicion']).strip()
            densidad_inicial = int(row['densidad_inicial'])
            
            # Normalizar especie: aceptar variaciones de Pinus y Eucalyptus
            especie_normalized = especie_raw.lower().strip()
            if especie_normalized in ['pinus', 'pino']:
                especie = 'Pinus'
            elif especie_normalized in ['eucalyptus', 'eucapyltus', 'eucalipto']:
                especie = 'Eucapyltus'
            else:
                rodales_invalidos.append(
                    f"Fila {idx+2}: Especie '{especie_raw}' inválida. "
                    f"Use 'Pinus' o 'Eucalyptus' (se aceptan variaciones en mayúsculas/minúsculas)"
                )
                continue
            
            # Manejo: convertir a 'NA' string para consistencia con lookup table (que usa keep_default_na=False)
            if pd.isna(manejo_raw) or str(manejo_raw).upper() == 'NA':
                manejo = 'NA'
            else:
                manejo = str(manejo_raw).strip()
            
            # Validar edad inicial
            if edad_inicial < 1:
                rodales_invalidos.append(
                    f"Fila {idx+2} ({id_rodal}): Edad inicial debe ser >= 1"
                )
                continue
            
            # Validar hectáreas
            if hectarea <= 0:
                rodales_invalidos.append(
                    f"Fila {idx+2} ({id_rodal}): Hectáreas debe ser > 0"
                )
                continue
            
            # Crear clave para lookup table
            # Mapear variaciones de condición
            condicion_map = {
                'con manejo': 'con manejo',
                'sin manejo': 'SinManejo',
                'sinmanejo': 'SinManejo',
                'conmanejo': 'con manejo',
                'postpodayraleo700-300': 'PostPodayRaleo700-300',
                'postraleo1250-700': 'PostRaleo1250-700',
            }
            condicion_normalizada = condicion_map.get(condicion.lower(), condicion)
            
            # Construir clave de búsqueda
            key = (especie, zona, site_index, manejo, condicion_normalizada, densidad_inicial)
            
            # Verificar que existe en lookup table
            if key not in dict_idx:
                rodales_invalidos.append(
                    f"Fila {idx+2} ({id_rodal}): Combinación no encontrada en lookup table: "
                    f"Especie={especie}, Zona={zona}, SiteIndex={site_index}, "
                    f"Manejo={manejo}, Condicion={condicion_normalizada}, DensidadInicial={densidad_inicial}"
                )
                continue
            
            # Validación adicional para Pinus: solo aceptar IDs de ecuaciones validadas
            if especie == 'Pinus':
                eq_id = dict_idx[key]
                if eq_id not in IDS_PINOS_INICIALES_VALIDOS:
                    rodales_invalidos.append(
                        f"Fila {idx+2} ({id_rodal}): Rodal de Pinus con ID de ecuación {eq_id} no validado. "
                        f"IDs validados: {IDS_PINOS_INICIALES_VALIDOS}"
                    )
                    continue
            
            # Verificar políticas factibles
            num_factibles = contar_politicas_factibles(
                especie, edad_inicial, horizonte, policies_pino, policies_eucalyptus
            )
            
            if num_factibles < 1:
                rodales_invalidos.append(
                    f"Fila {idx+2} ({id_rodal}): No hay políticas factibles para edad_inicial={edad_inicial} "
                    f"con horizonte={horizonte}"
                )
                continue
            
            # Si pasó todas las validaciones, agregar a listas
            ids_rodales.append(id_rodal)
            edades_iniciales.append(edad_inicial)
            hectareas.append(hectarea)
            especies_aleatorias.append(especie)
            zonas_aleatorias.append(zona)
            site_indices_aleatorios.append(site_index)
            densidades_iniciales_aleatorias.append(densidad_inicial)
            manejos_aleatorios.append(manejo)
            condiciones_aleatorias.append(condicion_normalizada)
            
            if especie == 'Pinus':
                pinos_count += 1
            else:
                eucas_count += 1
                
        except Exception as e:
            rodales_invalidos.append(
                f"Fila {idx+2}: Error al procesar: {str(e)}"
            )
            continue
    
    # Reportar rodales inválidos
    if rodales_invalidos:
        print(f"\n⚠️  Se encontraron {len(rodales_invalidos)} rodales con problemas:")
        for msg in rodales_invalidos[:10]:  # Mostrar máximo 10
            print(f"   - {msg}")
        if len(rodales_invalidos) > 10:
            print(f"   ... y {len(rodales_invalidos) - 10} más")
    
    # Verificar que se cargó al menos un rodal
    if len(ids_rodales) == 0:
        raise ValueError(
            "No se pudo cargar ningún rodal válido del archivo. "
            "Revisa los mensajes de error anteriores."
        )
    
    print(f"\n✓ Se cargaron {len(ids_rodales)} rodales válidos:")
    print(f"  - {pinos_count} rodales de Pinus")
    print(f"  - {eucas_count} rodales de Eucalyptus")
    
    # Crear el diccionario de configuración
    config = {
        "horizonte": horizonte,
        "rodales": len(ids_rodales),
        "edades": edades_iniciales,
        "has": hectareas,
        "especie": especies_aleatorias,
        "siteIndex": site_indices_aleatorios,
        "zona": zonas_aleatorias,
        "densidadInicial": densidades_iniciales_aleatorias,
        "manejo": manejos_aleatorios,
        "condición": condiciones_aleatorias,
        "id_rodal": ids_rodales,
        "num_policies_pino": len(policies_pino),
        "policies_pino": policies_pino,
        "num_policies_eucalyptus": len(policies_eucalyptus),
        "policies_eucalyptus": policies_eucalyptus,
    }
    
    return config

def contar_politicas_factibles(especie: str, edad_inicial: int, horizonte: int, policies_pino: List[Tuple[int, int]], policies_eucalyptus: List[Tuple[int,]]) -> int:
    """
    Cuenta cuántas políticas de manejo son factibles para un rodal
    dada su especie y edad inicial.
    """
    if especie == "Pinus":
        policies = policies_pino
    elif especie == "Eucapyltus":
        policies = policies_eucalyptus
    else:
        return 0

    contador_factibles = 0
    for policy in policies:
        es_factible = True
        if especie == "Pinus":
            if policy[0] - edad_inicial + 1 > horizonte and edad_inicial <= policy[0]:
                es_factible = False
            if edad_inicial > policy[1]:
                es_factible = False
        elif especie == "Eucapyltus":
            if policy[0] - edad_inicial + 1 > horizonte and edad_inicial <= policy[0]:
                es_factible = False
            if edad_inicial > policy[0]:
                es_factible = False
        
        if es_factible:
            contador_factibles += 1
            
    return contador_factibles

def generar_combinacion_valida(df: pd.DataFrame, especie_requerida: str = None) -> Tuple:
    """
    Genera una combinación válida de parámetros de rodal basada en la lookup table.
    """
    if especie_requerida == "Pinus":
        id_elegido = random.choice(IDS_PINOS_INICIALES_VALIDOS)
        fila_elegida = df[df['id'] == id_elegido]
        combinacion = fila_elegida.index[0]
        return combinacion

    especies = df.index.get_level_values('Especie').unique().tolist()
    zonas = df.index.get_level_values('Zona').unique().tolist()
    densidades_iniciales = df.index.get_level_values('DensidadInicial').unique().tolist()
    site_indices = df.index.get_level_values('SiteIndex').unique().tolist()
    manejos = df.index.get_level_values('Manejo').unique().tolist()
    condiciones = df.index.get_level_values('Condicion').unique().tolist()

    lookup_set = set(zip(df.index.get_level_values('Especie'),
                         df.index.get_level_values('Zona'),
                         df.index.get_level_values('SiteIndex'),
                         df.index.get_level_values('Manejo'),
                         df.index.get_level_values('Condicion'),
                         df.index.get_level_values('DensidadInicial')))

    while True:
        if especie_requerida:
            especie = especie_requerida
        else:
            especie = np.random.choice(especies)
        
        zona = np.random.choice(zonas)
        site_index = np.random.choice(site_indices)
        manejo = np.random.choice(manejos)
        condicion = np.random.choice(condiciones)
        densidad_inicial = np.random.choice(densidades_iniciales)

        combinacion = (especie, zona, site_index, manejo, condicion, densidad_inicial)

        if combinacion in lookup_set:
            if especie == "Pinus":
                try:
                    row = df.loc[combinacion]
                    if not pd.isnull(row.get("next", np.nan)):
                        return combinacion
                except:
                    continue
            else:
                return combinacion

def generar_rodales_aleatorios(
    df: pd.DataFrame,
    dict_idx: Dict,
    num_rodales: int,
    horizonte: int,
    policies_pino: List[Tuple[int, int]],
    policies_eucalyptus: List[Tuple[int,]]
) -> Dict[str, Any]:
    """
    Genera rodales aleatorios con proporción controlada de especies.
    
    Basado en la lógica original del código, genera entre 40-60% de pinos
    y el resto eucaliptos, asegurando que cada rodal tenga al menos 2 políticas factibles.
    """
    
    print(f"Generando {num_rodales} rodales con una proporción controlada (máx 60/40)...")

    # Determinar objetivos para cada especie (40-60% pinos)
    target_pinos = random.randint(int(num_rodales * 0.4), int(num_rodales * 0.6))
    target_eucas = num_rodales - target_pinos
    print(f"Objetivo de la simulación: {target_pinos} rodales de Pino, {target_eucas} rodales de Eucalipto.")

    # Listas para almacenar los datos de los rodales válidos
    edades_iniciales = []
    hectareas = []
    ids_rodales = []
    especies_aleatorias = []
    zonas_aleatorias = []
    site_indices_aleatorios = []
    densidades_iniciales_aleatorias = []
    manejos_aleatorios = []
    condiciones_aleatorias = []

    # Contadores
    pinos_generados = 0
    eucas_generados = 0

    # Bucle principal de generación
    while len(ids_rodales) < num_rodales:
        
        # Decidir qué especie generar según las cuotas
        if pinos_generados >= target_pinos:
            especie_aleatoria = "Eucapyltus"
        elif eucas_generados >= target_eucas:
            especie_aleatoria = "Pinus"
        else:
            especie_aleatoria = np.random.choice(["Pinus", "Eucapyltus"])

        # Generar edad inicial según especie
        if especie_aleatoria == "Pinus":
            edad_inicial = np.random.randint(1, 11)
        else:
            edad_inicial = np.random.randint(1, 21)

        # Verificar que tenga al menos 1 política factible
        num_factibles = contar_politicas_factibles(
            especie_aleatoria, edad_inicial, horizonte, policies_pino, policies_eucalyptus
        )
        
        if num_factibles < 1:
            continue

        # Generar combinación válida
        combinacion_valida = generar_combinacion_valida(df, especie_requerida=especie_aleatoria)
        especie, zona, site_index, manejo, condicion, densidad_inicial = combinacion_valida
        hectarea = round(np.random.uniform(1, 20), 2)

        # Añadir el rodal válido a nuestras listas
        num_actual = len(ids_rodales) + 1
        ids_rodales.append(f"stand{num_actual}")
        edades_iniciales.append(edad_inicial)
        hectareas.append(hectarea)
        especies_aleatorias.append(especie)
        zonas_aleatorias.append(zona)
        site_indices_aleatorios.append(site_index)
        densidades_iniciales_aleatorias.append(densidad_inicial)
        manejos_aleatorios.append(manejo)
        condiciones_aleatorias.append(condicion)
        
        # Actualizar contadores
        if especie_aleatoria == "Pinus":
            pinos_generados += 1
        else:
            eucas_generados += 1
    
    print(f"¡Generación completa! Se crearon {pinos_generados} rodales de Pino y {eucas_generados} de Eucalipto.")

    # Crear el diccionario de configuración
    config = {
        "horizonte": horizonte,
        "rodales": num_rodales,
        "edades": edades_iniciales,
        "has": hectareas,
        "especie": especies_aleatorias,
        "siteIndex": site_indices_aleatorios,
        "zona": zonas_aleatorias,
        "densidadInicial": densidades_iniciales_aleatorias,
        "manejo": manejos_aleatorios,
        "condición": condiciones_aleatorias,
        "id_rodal": ids_rodales,
        "num_policies_pino": len(policies_pino),
        "policies_pino": policies_pino,
        "num_policies_eucalyptus": len(policies_eucalyptus),
        "policies_eucalyptus": policies_eucalyptus,
    }

    return config

def generar_rodales(config: Dict[str, Any], df: pd.DataFrame, dict_idx: Dict) -> List[pd.Series]:
    """
    Genera lista de rodales como Series de pandas basado en la configuración.
    """
    rodales = []
    for i in range(config["rodales"]):
        key = (
            config["especie"][i],
            config["zona"][i],
            config["siteIndex"][i],
            config["manejo"][i],
            config["condición"][i],
            config["densidadInicial"][i],
        )
        if key not in dict_idx:
            raise KeyError(
                f"No existe un índice para la combinación de claves {key} en la lookup table."
            )
        init_ages = config["edades"][i]
        hectareas = config["has"][i]
        rodal_id = config["id_rodal"][i]
        especie = config["especie"][i]
        rodal = pd.concat(
            (
                df.loc[key],
                pd.Series(
                    {
                        "eq_id": dict_idx[key],
                        "edad_in": init_ages,
                        "ha": hectareas,
                        "id_rodal": rodal_id,
                        "TipoEspecie": especie,
                    }
                ),
            )
        )
        rodales.append(rodal)
    return rodales

def generar_rodalesconpolicy(
    rodales: List[pd.Series], 
    config: Dict[str, Any]
) -> List[pd.Series]:
    """
    Genera rodales con políticas de manejo aplicadas.
    """
    horizonte = config["horizonte"]
    rodales_con_policy = []
    
    for rodal in rodales:
        if rodal["TipoEspecie"] == "Pinus":
            policies = config["policies_pino"]
        elif rodal["TipoEspecie"] == "Eucapyltus":
            policies = config["policies_eucalyptus"]
        else:
            continue
        
        for i, policy in enumerate(policies):
            es_factible = True
            if rodal["TipoEspecie"] == "Pinus":
                if policy[0] - rodal["edad_in"] + 1 > horizonte and rodal["edad_in"] <= policy[0]:
                    es_factible = False
                if rodal["edad_in"] > policy[1]:
                    es_factible = False
            elif rodal["TipoEspecie"] == "Eucapyltus":
                if policy[0] - rodal["edad_in"] + 1 > horizonte and rodal["edad_in"] <= policy[0]:
                    es_factible = False
                if rodal["edad_in"] > policy[0]:
                    es_factible = False
            
            if not es_factible:
                continue

            rodal_policy = rodal.copy()
            rodal_policy['policy_number'] = i + 1

            rodal_policy['ya_fue_raleado_al_inicio'] = False
            if rodal["TipoEspecie"] == "Pinus":
                if rodal["edad_in"] > policy[0]:
                    rodal_policy['ya_fue_raleado_al_inicio'] = True
            
            poda_raleo_periodos = []
            cosecha_periodos = []
            edad_rodal = rodal["edad_in"]

            for periodo in range(1, horizonte + 1):
                if rodal["TipoEspecie"] == "Pinus":
                    if edad_rodal == policy[0]:
                        poda_raleo_periodos.append(periodo)
                    if edad_rodal == policy[1]:
                        cosecha_periodos.append(periodo)
                        edad_rodal = 0
                elif rodal["TipoEspecie"] == "Eucapyltus":
                    if edad_rodal == policy[0]:
                        cosecha_periodos.append(periodo)
                        edad_rodal = 0
                edad_rodal += 1
            
            rodal_policy["poda_raleo"] = poda_raleo_periodos
            rodal_policy["cosecha"] = cosecha_periodos
            rodal_policy["horizonte"] = horizonte
            rodales_con_policy.append(rodal_policy)

    return rodales_con_policy
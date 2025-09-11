#!/usr/bin/env python
# coding: utf-8

# In[ ]:


# treemun_sim/core.py
"""
Función principal del simulador forestal.
"""

import pandas as pd
import numpy as np
import random
from typing import List, Tuple, Dict, Any
import pkg_resources
from .generadores import generar_rodales_aleatorios, generar_rodales, generar_rodalesconpolicy
from .simulacion import simula_bosque as simula_bosque_interno, getBiomasa4Opti

# Semilla global para reproducibilidad
SEMILLA_GLOBAL = 5555

def cargar_lookup_table():
    """Carga la tabla de lookup incluida en el paquete."""
    try:
        ruta_archivo = pkg_resources.resource_filename('treemun_sim', 'data/lookup_table.csv')
        df = pd.read_csv(ruta_archivo, keep_default_na=False)
        df.set_index(
            ["Especie", "Zona", "SiteIndex", "Manejo", "Condicion", "DensidadInicial"],
            inplace=True
        )
        dict_idx = df["id"].to_dict()
        return df, dict_idx
    except Exception as e:
        raise FileNotFoundError(f"No se pudo cargar lookup_table.csv: {e}")

def simular_bosque(
    policies_pino: List[Tuple[int, int]] = None,
    policies_eucalyptus: List[Tuple[int,]] = None,
    horizonte: int = 30,
    num_rodales: int = 100,
    semilla: int = None
) -> Tuple[List, List, Dict, Dict]:
    """
    Función principal del simulador forestal.
    
    Args:
        policies_pino: Lista de políticas para pino, formato [(raleo, cosecha), ...]
                      Por defecto: [(9, 18), (9, 20), ..., (12, 24)]
        policies_eucalyptus: Lista de políticas para eucalipto, formato [(cosecha,), ...]
                            Por defecto: [(9,), (10,), (11,), (12,)]
        horizonte: Horizonte temporal de la simulación (años)
        num_rodales: Número de rodales a generar
        semilla: Semilla para reproducibilidad. Si es None, usa SEMILLA_GLOBAL (5555)
        
    Returns:
        Tupla con (bosque, resumen, biomasa_final_por_rodal, biomasa_estimada)
    """
    
    # Establecer semilla (usar valor por defecto si no se especifica)
    if semilla is None:
        semilla = SEMILLA_GLOBAL
    
    np.random.seed(semilla)
    random.seed(semilla)
    
    # Políticas por defecto si no se especifican
    if policies_pino is None:
        policies_pino = [
            (9, 18), (9, 20), (9, 22), (9, 24),
            (10, 18), (10, 20), (10, 22), (10, 24),
            (11, 18), (11, 20), (11, 22), (11, 24),
            (12, 18), (12, 20), (12, 22), (12, 24)
        ]
    
    if policies_eucalyptus is None:
        policies_eucalyptus = [(9,), (10,), (11,), (12,)]
    
    # Cargar datos base
    df, dict_idx = cargar_lookup_table()
    
    # Generar configuración de rodales aleatorios
    config = generar_rodales_aleatorios(
        df=df,
        dict_idx=dict_idx,
        num_rodales=num_rodales,
        horizonte=horizonte,
        policies_pino=policies_pino,
        policies_eucalyptus=policies_eucalyptus
    )
    
    # Generar rodales base
    rodales = generar_rodales(config, df, dict_idx)
    
    # Aplicar políticas
    rodales_con_policy = generar_rodalesconpolicy(rodales, config)
    
    # Simular crecimiento
    bosque, resumen, biomasa_final_por_rodal = simula_bosque_interno(
        rodales_con_policy, df, config["horizonte"]
    )
    
    # Generar datos para optimización
    biomasa_estimada = getBiomasa4Opti(bosque, resumen)
    
    return bosque, resumen, biomasa_final_por_rodal, biomasa_estimada


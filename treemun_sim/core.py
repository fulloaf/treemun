#!/usr/bin/env python
# coding: utf-8

# treemun_sim/core.py
"""
Función principal del simulador forestal.

La contabilidad de carbono se implementa como una capa opcional de
postprocesamiento. No modifica el simulador de crecimiento/rendimiento.
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
    archivo_rodales: str = None,
    policies_pino: List[Tuple[int, int]] = None,
    policies_eucalyptus: List[Tuple[int,]] = None,
    horizonte: int = 30,
    num_rodales: int = 100,
    semilla: int = None,
    Carbon: bool = False,
    return_carbon_opti: bool = False,
    carbon_opti_column: str = "CarbSeqOPT",
    carbon_kwargs: Dict[str, Any] = None,
) -> Tuple:
    """
    Función principal del simulador forestal.

    Args:
        archivo_rodales: Ruta a archivo CSV/TXT con información de rodales.
                        Si se especifica, se ignora num_rodales y se cargan
                        los rodales del archivo. Columnas requeridas:
                        id_rodal, hectareas, especie, edad_inicial, zona,
                        site_index, manejo, condicion, densidad_inicial.
        policies_pino: Lista de políticas para pino, formato
                      [(raleo, cosecha), ...]. Por defecto:
                      [(9, 18), (9, 20), ..., (12, 24)].
        policies_eucalyptus: Lista de políticas para eucalipto, formato
                            [(cosecha,), ...]. Por defecto:
                            [(9,), (10,), (11,), (12,)].
        horizonte: Horizonte temporal de la simulación (años).
        num_rodales: Número de rodales a generar aleatoriamente
                    (ignorado si archivo_rodales es especificado).
        semilla: Semilla para reproducibilidad. Si es None, usa
                SEMILLA_GLOBAL (5555).
        Carbon: Si True, agrega a cada DataFrame de ``bosque`` las columnas
                del proxy de carbono. Si False, mantiene la salida original.
        return_carbon_opti: Si True, retorna un quinto objeto con el
                            diccionario de carbono para optimización.
                            Requiere Carbon=True.
        carbon_opti_column: Columna usada para construir el diccionario de
                            optimización de carbono. Por defecto usa
                            ``CarbSeqOPT`` en Mg C. Para CO2e se puede usar
                            ``CarbEqvOPT``.
        carbon_kwargs: Argumentos opcionales para ``CarbonSequestrationProxy``.

    Returns:
        Si return_carbon_opti=False:
            (bosque, resumen, biomasa_final_por_rodal, biomasa_estimada)

        Si return_carbon_opti=True:
            (bosque, resumen, biomasa_final_por_rodal, biomasa_estimada,
             carbon_estimada)

    Notes:
        La capa de carbono es un postprocesamiento. No modifica la simulación
        de crecimiento/rendimiento ni la lógica original de ``bioOPT``.
    """

    if return_carbon_opti and not Carbon:
        raise ValueError(
            "return_carbon_opti=True requiere Carbon=True. "
            "Active Carbon=True para calcular el proxy de carbono."
        )

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

    # Generar configuración de rodales
    if archivo_rodales is not None:
        # Cargar desde archivo
        from .generadores import cargar_rodales_desde_archivo
        config = cargar_rodales_desde_archivo(
            archivo=archivo_rodales,
            df=df,
            dict_idx=dict_idx,
            horizonte=horizonte,
            policies_pino=policies_pino,
            policies_eucalyptus=policies_eucalyptus
        )
    else:
        # Generar aleatoriamente
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

    # Generar datos para optimización.
    # Esta es la salida original basada en bioOPT.
    biomasa_estimada = getBiomasa4Opti(bosque, resumen)

    # Capa opcional de postprocesamiento de carbono.
    # Si Carbon=False, no se calcula nada adicional y se mantiene la salida original.
    carbon_estimada = None

    if Carbon:
        from .carbon import CarbonSequestrationProxy

        if carbon_kwargs is None:
            carbon_kwargs = {}

        carbon_proxy = CarbonSequestrationProxy(**carbon_kwargs)

        # Agrega columnas de carbono a cada DataFrame de bosque.
        # No modifica el simulador de crecimiento/rendimiento.
        bosque = carbon_proxy.add_to_bosque(bosque)

        # Exporta el parámetro de carbono para optimización solo si se solicita.
        # Por defecto exporta CarbSeqOPT, es decir, el cambio neto de carbono
        # post-operación en Mg C, únicamente en periodos operacionales.
        if return_carbon_opti:
            carbon_estimada = carbon_proxy.opt_period_dict(
                bosque,
                column=carbon_opti_column,
                reference_keys=biomasa_estimada.keys(),
            )

    if return_carbon_opti:
        return (
            bosque,
            resumen,
            biomasa_final_por_rodal,
            biomasa_estimada,
            carbon_estimada,
        )

    return bosque, resumen, biomasa_final_por_rodal, biomasa_estimada

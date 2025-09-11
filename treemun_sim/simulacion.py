#!/usr/bin/env python
# coding: utf-8

# In[ ]:


# simulador_forestal/simulacion.py
"""
Módulo para la simulación del crecimiento forestal y cálculo de biomasa.
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any, Tuple

def calc_biomasa(rodal: pd.Series, e: int) -> float:
    """
    Calcula la biomasa para un rodal a una edad específica usando ecuaciones alométricas.
    """
    return max(rodal["α"] * e ** rodal["β"] + rodal["γ"], 0)

def rotular_condicion(
    edad_poda_raleo: List[int],  
    edad_cosecha: List[int],  
    edades_updated: pd.Series
) -> pd.Series:
    """
    Rotula la condición de manejo para cada edad del rodal.
    """
    condiciones = []
    
    if not edad_poda_raleo:
        edad_poda_raleo = [float('inf')]
    if not edad_cosecha:
        edad_cosecha = [float('inf')]
    
    for edad in edades_updated:
        if edad < min(edad_poda_raleo):
            condiciones.append("sin manejo")
        elif edad in edad_poda_raleo:
            condiciones.append("con manejo")
        elif edad >= max(edad_poda_raleo) and edad <= max(edad_cosecha):
            condiciones.append("con manejo")
        else:
            condiciones.append("sin manejo")

    return pd.Series(condiciones)

def generar_codigo_kitral(especie: str, edad: int, condición: str) -> str:
    """
    Genera códigos Kitral basados en especie, edad y condición de manejo.
    """
    key = (especie, edad, condición)
    
    if key[0] == "Pinus":
        if key[1] <= 3:
            value = "PL01" if key[2] == "sin manejo" else "NoCode"
        elif 3 < key[1] <= 11:
            value = "PL02" if key[2] == "sin manejo" else "PL05"
        elif 11 < key[1] <= 17:
            value = "PL03" if key[2] == "sin manejo" else "PL06"
        elif key[1] > 17:
            value = "PL04" if key[2] == "sin manejo" else "PL07"
        else:
            value = "NoCode"
    
    elif key[0] == "Eucapyltus":
        if key[1] <= 3:
            value = "PL08"
        elif 3 < key[1] <= 10:
            value = "PL09"
        else:
            value = "PL10"
    
    else:
        raise ValueError(f"Especie no soportada: {key[0]}")
    
    return value

def simula_bosque(
    rodales_con_policy: List[pd.Series],
    df: pd.DataFrame,
    horizonte: int
) -> Tuple[List[pd.DataFrame], List[Dict], Dict]:
    """
    Simula el crecimiento del bosque para todos los rodales con sus políticas aplicadas.
    
    Esta es tu función original 'simula_bosque' adaptada.
    """
    bosque = []
    resumen = []
    biomasa_final_por_rodal = {}

    for rodal in rodales_con_policy:
        tabla = pd.DataFrame()
        tabla["periodo"] = range(1, horizonte + 1)
        tabla["edadRodal"] = range(rodal["edad_in"], rodal["edad_in"] + horizonte)
        tabla["edad_updated"] = tabla["edadRodal"]

        cosecha_indices = [
            tabla[tabla["periodo"] == c].index[0] for c in rodal["cosecha"] if c in tabla["periodo"].values
        ]

        for cosecha_index in cosecha_indices:
            longitud = len(tabla.loc[cosecha_index + 1:, "edad_updated"])
            if longitud > 0:
                valores = range(1, longitud + 1)
                tabla.loc[cosecha_index + 1:, "edad_updated"] = valores

        edad_poda_raleo = [
            tabla.loc[tabla["periodo"] == pr, "edad_updated"].values[0]
            for pr in rodal["poda_raleo"] if pr in tabla["periodo"].values
        ] if isinstance(rodal["poda_raleo"], list) else []
        
        edad_cosecha = [
            tabla.loc[tabla["periodo"] == pc, "edad_updated"].values[0]
            for pc in rodal["cosecha"] if pc in tabla["periodo"].values
        ] if isinstance(rodal["cosecha"], list) else []

        tabla["condición"] = rotular_condicion(
            edad_poda_raleo, edad_cosecha, tabla["edad_updated"]
        )
        
        biomasa = []
        if rodal["TipoEspecie"] == "Eucapyltus" or pd.isnull(rodal.get("next")) or rodal["next"] == "":
            for e in tabla["edad_updated"]:
                biomasa.append(calc_biomasa(rodal, e))
        else:
            next_rodal = df[df["id"] == int(rodal["next"])].squeeze()
            poda_raleo_index = 0
            cosecha_index = 0
            usa_curva_next = rodal.get('ya_fue_raleado_al_inicio', False)

            for e in tabla["edad_updated"]:
                if cosecha_index < len(edad_cosecha) and e == edad_cosecha[cosecha_index]:
                    if usa_curva_next:
                        biomasa.append(calc_biomasa(next_rodal, e))
                    else:
                        biomasa.append(calc_biomasa(rodal, e))
                    usa_curva_next = False
                    cosecha_index += 1
                    continue
                if poda_raleo_index < len(edad_poda_raleo) and e == edad_poda_raleo[poda_raleo_index]:
                    biomasa.append(calc_biomasa(rodal, e))
                    poda_raleo_index += 1
                    usa_curva_next = True
                    continue
                if usa_curva_next:
                    biomasa.append(calc_biomasa(next_rodal, e))
                else:
                    biomasa.append(calc_biomasa(rodal, e))

        tabla["biomasa"] = (pd.Series(biomasa) * rodal["ha"]).round(3)
        tabla["id_rodal"] = rodal["id_rodal"]
        tabla["Especie"] = rodal["TipoEspecie"]

        tabla["kitral_class"] = tabla.apply(
            lambda row: generar_codigo_kitral(
                row["Especie"], row["edad_updated"], row["condición"]
            ),
            axis=1,
        )

        edad_initial = tabla.loc[0, "edad_updated"]
        edad_final = tabla.loc[horizonte - 1, "edad_updated"]

        policy_num = rodal['policy_number']
        if rodal["TipoEspecie"] == "Pinus":
            politica = f"policy_pino {policy_num}"
        elif rodal["TipoEspecie"] == "Eucapyltus":
            politica = f"policy_eucalyptus {policy_num}"
        else:
            raise ValueError(f"La especie {rodal['TipoEspecie']} no tiene políticas definidas.")
        
        tabla["politica"] = politica
        tabla["bioOPT"] = 0.0

        # Cálculo de bioOPT para podas/raleos
        for pr in rodal["poda_raleo"] if isinstance(rodal["poda_raleo"], list) else []:
            if pr in tabla["periodo"].values and pr != -1:
                valor_bio_opt = 0.0
                if pd.notnull(rodal.get("next")) and rodal["next"] != "":
                    edad_en_raleo = tabla.loc[tabla["periodo"] == pr, "edad_updated"].values[0]
                    try:
                        next_rodal_df = df[df["id"] == int(rodal["next"])]
                        if not next_rodal_df.empty:
                            next_rodal = next_rodal_df.squeeze()
                            biomasa_antes_ha = calc_biomasa(rodal, edad_en_raleo)
                            biomasa_despues_ha = calc_biomasa(next_rodal, edad_en_raleo)
                            diferencia_ha = biomasa_antes_ha - biomasa_despues_ha
                            if diferencia_ha >= 0:
                                valor_bio_opt = diferencia_ha * rodal["ha"]
                            else:
                                biomasa_total_antes = tabla.loc[tabla["periodo"] == pr, "biomasa"].values[0]
                                valor_bio_opt = biomasa_total_antes * 0.30
                        else:
                            biomasa_total_antes = tabla.loc[tabla["periodo"] == pr, "biomasa"].values[0]
                            valor_bio_opt = biomasa_total_antes * 0.30
                    except Exception:
                        biomasa_total_antes = tabla.loc[tabla["periodo"] == pr, "biomasa"].values[0]
                        valor_bio_opt = biomasa_total_antes * 0.30
                else:
                    biomasa_total_antes = tabla.loc[tabla["periodo"] == pr, "biomasa"].values[0]
                    valor_bio_opt = biomasa_total_antes * 0.30
                tabla.loc[tabla["periodo"] == pr, "bioOPT"] = valor_bio_opt
        
        # Cálculo de bioOPT para cosechas
        for pc in rodal["cosecha"] if isinstance(rodal["cosecha"], list) else []:
            if pc in tabla["periodo"].values:
                tabla.loc[tabla["periodo"] == pc, "bioOPT"] = tabla.loc[tabla["periodo"] == pc, "biomasa"].values[0]
        
        tabla = tabla.drop(columns=["edadRodal"])
        tabla = tabla.rename(columns={"edad_updated": "edad_rodal"})
        
        if horizonte in tabla["periodo"].values:
            biomasa_final_por_rodal[(rodal["id_rodal"], politica)] = (
                tabla.loc[tabla["periodo"] == horizonte, "biomasa"].values[0]
            )
        
        bosque.append(tabla)

        resumen.append(
            {
                "id_rodal": rodal["id_rodal"],
                "especie": rodal["TipoEspecie"],
                "has": rodal["ha"],
                "edad_inicial": edad_initial,
                "edad_final": edad_final,
                "policy": politica,
                "ecuacion_inicial_id": rodal["eq_id"]
            }
        )

    return bosque, resumen, biomasa_final_por_rodal

def getBiomasa4Opti(bosque: List[pd.DataFrame], resumen: List[Dict]) -> Dict:
    """
    Prepara los datos de biomasa para optimización.
    
    Esta es tu función original 'getBiomasa4Opti'.
    """
    biomasa_list = [df["bioOPT"].values for df in bosque]
    biomasa_df = pd.DataFrame(biomasa_list).T
    
    id_rodales = [item['id_rodal'] for item in resumen]
    policies = [item['policy'] for item in resumen]
    especies = [item["especie"] for item in resumen]

    df_test = pd.DataFrame([id_rodales, policies, especies])
    biomasa_df.columns = df_test.columns
    
    combined_df = pd.concat([df_test, biomasa_df], axis=0)
    combined_df.index = ['id_rodal', 'policy', "especie"] + [i+1 for i in range(len(biomasa_df))]
    
    combined_df.columns = pd.MultiIndex.from_arrays([combined_df.iloc[0], combined_df.iloc[1], combined_df.iloc[2]])
    combined_df = combined_df.drop(combined_df.index[[0, 1, 2]])

    # Conversión a diccionario para optimización
    a_I_J_dict = {
        k: v for k, v in 
        combined_df.stack()
                   .stack()
                   .stack()
                   .to_dict().items()
        if not pd.isna(v) and v > 0  # Filtrar valores nulos y ceros
    }
    
    return a_I_J_dict

def simula_bosque_completo(
    config: Dict[str, Any],
    df: pd.DataFrame,
    dict_idx: Dict
) -> Tuple[List[pd.DataFrame], List[Dict], Dict]:
    """
    Función que integra todo el proceso de simulación.
    
    Equivale a ejecutar secuencialmente:
    1. generar_rodales()
    2. generar_rodalesconpolicy() 
    3. simula_bosque()
    """
    from .generadores import generar_rodales, generar_rodalesconpolicy
    
    # Generar rodales base
    rodales = generar_rodales(config, df, dict_idx)
    
    # Aplicar políticas
    rodales_con_policy = generar_rodalesconpolicy(rodales, config)
    
    # Simular crecimiento
    bosque, resumen, biomasa_final_por_rodal = simula_bosque(
        rodales_con_policy, df, config["horizonte"]
    )
    
    return bosque, resumen, biomasa_final_por_rodal


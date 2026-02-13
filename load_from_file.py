#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Ejemplo: Cargar bosque desde archivo CSV
=========================================

Este ejemplo muestra cómo usar treemun-sim con un bosque cargado desde archivo,
en lugar de generar rodales aleatorios.
"""

import treemun_sim as tm
import os

# Ruta al archivo de ejemplo (ajusta según tu ubicación)
archivo_rodales = "ejemplo_rodales.csv"

# Verificar que el archivo existe
if not os.path.exists(archivo_rodales):
    print(f"ERROR: No se encuentra el archivo {archivo_rodales}")
    print("Asegúrate de tener el archivo en el directorio actual")
    exit(1)

print("=" * 70)
print("SIMULACIÓN DE BOSQUE DESDE ARCHIVO")
print("=" * 70)

# Parámetros de simulación
horizonte = 30  # años

# Políticas a evaluar
policies_pino = [
    (9, 18), (10, 20), (11, 22), (12, 24)  # (edad_raleo, edad_cosecha)
]
policies_eucalyptus = [
    (9,), (10,), (11,), (12,)  # (edad_cosecha,)
]

# Simular bosque cargando desde archivo
print(f"\n1. Cargando rodales desde '{archivo_rodales}'...")
forest, summary, final_biomass, collected_biomass = tm.simular_bosque(
    archivo_rodales=archivo_rodales,  # ← NUEVO PARÁMETRO
    policies_pino=policies_pino,
    policies_eucalyptus=policies_eucalyptus,
    horizonte=horizonte
)

print(f"\n2. Resumen de la simulación:")
print(f"   - Total de combinaciones rodal-política: {len(forest)}")
print(f"   - Horizonte de planificación: {horizonte} años")

# Ver información del primer rodal
print(f"\n3. Ejemplo de salida - Primer rodal con política 1:")
primer_rodal = forest[0]
print(f"   - ID Rodal: {primer_rodal['id_rodal'].iloc[0]}")
print(f"   - Especie: {primer_rodal['Especie'].iloc[0]}")
print(f"   - Política: {primer_rodal['politica'].iloc[0]}")
print(f"   - Área: {primer_rodal['ha'].iloc[0]:.2f} ha")
print(f"   - Biomasa final: {primer_rodal['biomasa'].iloc[-1]:.2f} m³")

# Crear modelo de optimización
print(f"\n4. Creando modelo de optimización...")
model = tm.forest_management_optimization_model(
    bosque=forest,
    a_i_j_T=final_biomass,
    a_i_j_t=collected_biomass,
    horizon=horizonte,
    pine_revenue=12,           # $/m³
    eucalyptus_revenue=10,     # $/m³
    min_ending_biomass=5000,   # m³
    discount_rate=0.08         # 8% anual
)

print("   ✓ Modelo creado exitosamente")

# Resolver modelo
print(f"\n5. Resolviendo modelo de optimización...")
results = tm.solve_model(model, solver_name='cbc', gap=0.01)

# Extraer resultados
solution = tm.extract_results(model, results)

if solution:
    print(f"\n6. RESULTADOS DE LA OPTIMIZACIÓN:")
    print(f"   {'=' * 60}")
    print(f"   VPN Óptimo: ${solution['objective_value']:,.2f}")
    print(f"   Rodales de Pino gestionados: {solution['total_pinus_stand_treated']}")
    print(f"   Rodales de Eucalipto gestionados: {solution['total_eucalyptus_stand_treated']}")
    print(f"\n   Plan de cosecha por periodo:")
    for periodo, biomasa in enumerate(solution['total_harvest_per_period'], 1):
        print(f"      Periodo {periodo:2d}: {biomasa:8.2f} m³")
    
    print(f"\n   Plan de gestión seleccionado para rodales de Pino:")
    for rodal_id, politica in list(solution['pinus_stand_plan'].items())[:5]:
        print(f"      {rodal_id}: Política {politica}")
    
    if solution['total_eucalyptus_stand_treated'] > 0:
        print(f"\n   Plan de gestión seleccionado para rodales de Eucalipto:")
        for rodal_id, politica in list(solution['eucalyptus_stand_plan'].items())[:5]:
            print(f"      {rodal_id}: Política {politica}")
else:
    print("\n   ⚠️  No se pudo resolver el modelo de optimización")

print("\n" + "=" * 70)
print("SIMULACIÓN COMPLETADA")
print("=" * 70)

#!/usr/bin/env python
# coding: utf-8

# In[ ]:


#to get __init__.py
"""
Simulador Forestal - Paquete para simulación de crecimiento forestal

Este paquete proporciona herramientas para simular el crecimiento forestal
y optimizar políticas de manejo para diferentes especies (Pinus y Eucalyptus).

Uso básico:
    import simulador_forestal as sf
    
    # Simulación con parámetros por defecto
    bosque, resumen, biomasa_final, biomasa_estimada = sf.simular_bosque()
    
    # Simulación personalizada
    bosque, resumen, biomasa_final, biomasa_estimada = sf.simular_bosque(
        policies_pino=[(9, 18), (10, 20)],
        policies_eucalyptus=[(9,), (10,)],
        horizonte=25,
        num_rodales=50,
        semilla=1234
    )

Autor: Felipe Ulloa-Fierro
Versión: 1.0.0
"""

# Importar la función principal que los usuarios van a usar
from .core import simular_bosque

# Metadata del paquete
__version__ = "1.0.0"
__author__ = "Felipe Ulloa-Fierro"

# Solo exponemos la función principal para mantener una API limpia
__all__ = ["simular_bosque"]


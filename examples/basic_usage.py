#!/usr/bin/env python
# coding: utf-8

# In[ ]:


#!/usr/bin/env python3
"""
Basic usage example of Treemun
Forest simulation with default parameters
"""

import treemun_sim as tm

def main():
    print("=== Treemun - basic example ===")
    print("Running simulation with default parameters...")
    
    # Basic simulation
    bosque, resumen, biomasa_final_por_rodal, biomasa_estimada = tm.simular_bosque()
    
    # Show results
    print(f"\nSimulation completed!")
    print(f"Stand-policy combinations generated: {len(bosque)}")
    print(f"Unique stands: {len(set([r['id_rodal'] for r in resumen]))}")
    print(f"Optimization data points: {len(biomasa_estimada)}")
    
    # Species analysis
    especies = [r['especie'] for r in resumen]
    pinos = especies.count('Pinus')
    eucaliptos = especies.count('Eucapyltus')
    
    print(f"\nSpecies distribution:")
    print(f"   Pines: {pinos} combinations")
    print(f"   Eucalyptus: {eucaliptos} combinations")
    
    # Show some example stands
    print(f"\nFirst 3 stands:")
    for i, df in enumerate(bosque[:3]):
        especie = df['Especie'].iloc[0]
        politica = df['politica'].iloc[0]
        biomasa_inicial = df['biomasa'].iloc[0]
        biomasa_final = df['biomasa'].iloc[-1]
        
        print(f"   Stand {i+1}: {especie} | {politica}")
        print(f"     Initial biomass: {biomasa_inicial:.2f} tons")
        print(f"     Final biomass: {biomasa_final:.2f} tons")
    
    # Final biomass statistics
    valores_biomasa = list(biomasa_final_por_rodal.values())  # Usar el nombre correcto
    if valores_biomasa:
        import numpy as np
        print(f"\nFinal biomass statistics (tons):")
        print(f"   Average: {np.mean(valores_biomasa):.2f}")
        print(f"   Minimum: {np.min(valores_biomasa):.2f}")
        print(f"   Maximum: {np.max(valores_biomasa):.2f}")
    
    print(f"\nSimulation completed successfully!")

if __name__ == "__main__":
    main()


# In[ ]:





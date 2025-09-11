#!/usr/bin/env python
# coding: utf-8

# In[ ]:


#!/usr/bin/env python3
"""
Custom policies example for Treemun
Comparison between different management strategies
"""

import treemun_sim as tm

def main():
    print("=== Treemun - custom policies ===")
    
    # Define different strategies
    print("Defining management strategies...")
    
    # Conservative strategy (long rotations)
    policies_pino_conservative = [(11, 22), (12, 24)]
    policies_eucalyptus_conservative = [(11,), (12,)]
    
    # Intensive strategy (short rotations)
    policies_pino_intensive = [(9, 18), (9, 20), (10, 18)]
    policies_eucalyptus_intensive = [(9,), (10,)]
    
    # Intermediate strategy
    policies_pino_intermediate = [(10, 20), (11, 21), (10, 22)]
    policies_eucalyptus_intermediate = [(10,), (11,)]
    
    # Common parameters
    horizonte = 25
    num_rodales = 30
    semilla = 2024
    
    # Simulate conservative strategy
    print("\n1. Simulating CONSERVATIVE strategy...")
    forest_conservative, summary_conservative, biomass_final_conservative, _ = tm.simular_bosque(
        policies_pino=policies_pino_conservative,
        policies_eucalyptus=policies_eucalyptus_conservative,
        horizonte=horizonte,
        num_rodales=num_rodales,
        semilla=semilla
    )
    
    # Simulate intensive strategy
    print("2. Simulating INTENSIVE strategy...")
    forest_intensive, summary_intensive, biomass_final_intensive, _ = tm.simular_bosque(
        policies_pino=policies_pino_intensive,
        policies_eucalyptus=policies_eucalyptus_intensive,
        horizonte=horizonte,
        num_rodales=num_rodales,
        semilla=semilla
    )
    
    # Simulate intermediate strategy
    print("3. Simulating INTERMEDIATE strategy...")
    forest_intermediate, summary_intermediate, biomass_final_intermediate, _ = tm.simular_bosque(
        policies_pino=policies_pino_intermediate,
        policies_eucalyptus=policies_eucalyptus_intermediate,
        horizonte=horizonte,
        num_rodales=num_rodales,
        semilla=semilla
    )
    
    # Comparative analysis
    print("\n" + "="*60)
    print("COMPARATIVE ANALYSIS")
    print("="*60)
    
    def analyze_strategy(name, final_biomass, summary):
        values = list(final_biomass.values())
        if values:
            import numpy as np
            average = np.mean(values)
            maximum = np.max(values)
            minimum = np.min(values)
            
            print(f"\n{name}:")
            print(f"  Generated combinations: {len(summary)}")
            print(f"  Average final biomass: {average:.2f} tons")
            print(f"  Maximum biomass: {maximum:.2f} tons")
            print(f"  Minimum biomass: {minimum:.2f} tons")
            
            return average
        return 0
    
    # Analyze each strategy
    avg_conservative = analyze_strategy("CONSERVATIVE", biomass_final_conservative, summary_conservative)
    avg_intensive = analyze_strategy("INTENSIVE", biomass_final_intensive, summary_intensive)
    avg_intermediate = analyze_strategy("INTERMEDIATE", biomass_final_intermediate, summary_intermediate)
    
    # Determine best strategy
    strategies = {
        "Conservative": avg_conservative,
        "Intensive": avg_intensive,
        "Intermediate": avg_intermediate
    }
    
    best_strategy = max(strategies, key=strategies.get)
    best_value = strategies[best_strategy]
    
    print(f"\nBEST STRATEGY: {best_strategy}")
    print(f"   Average biomass: {best_value:.2f} tons")
    
    # Species analysis
    print(f"\nSPECIES ANALYSIS:")
    
    def analyze_by_species(summary, final_biomass, strategy_name):
        species_info = {}
        for r in summary:
            species = r['especie']
            if species not in species_info:
                species_info[species] = []
            
            # Find corresponding final biomass
            for (stand_id, policy), biomass in final_biomass.items():
                if stand_id == r['id_rodal']:
                    species_info[species].append(biomass)
                    break
        
        for species, biomasses in species_info.items():
            if biomasses:
                import numpy as np
                average = np.mean(biomasses)
                print(f"  {strategy_name} - {species}: {average:.2f} tons average")
    
    analyze_by_species(summary_conservative, biomass_final_conservative, "Conservative")
    analyze_by_species(summary_intensive, biomass_final_intensive, "Intensive")
    analyze_by_species(summary_intermediate, biomass_final_intermediate, "Intermediate")
    
    print(f"\nComparative analysis completed!")

if __name__ == "__main__":
    main()


# In[ ]:





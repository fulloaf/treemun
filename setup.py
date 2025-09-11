#!/usr/bin/env python
# coding: utf-8

# In[ ]:


# setup.py
from setuptools import setup, find_packages
import os

# Leer el README para la descripción larga
this_directory = os.path.abspath(os.path.dirname(__file__))
try:
    with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
        long_description = f.read()
except FileNotFoundError:
    long_description = "Simulador de crecimiento y rendimiento forestal para evaluar políticas de manejo en la gestión de plantaciones"

setup(
    name="treemun-sim",
    version="1.0.0",
    author="Felipe Ulloa-Fierro",
    author_email="felipe.ulloa@utalca.cl", 
    description="Simulador de crecimiento y rendimiento forestal para evaluar políticas de manejo en la gestión de plantaciones",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/fulloaf/treemun",  
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Information Analysis",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
    install_requires=[
        "numpy>=1.19.0",
        "pandas>=1.2.0",
    ],
    include_package_data=True,
    package_data={
        "treemun_sim": ["data/*.csv"],
    },
    # Dependencias opcionales para desarrollo
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-cov>=2.0",
            "black>=21.0",
            "flake8>=3.8",
        ],
    },
    # Metadatos adicionales
    keywords="plantation forest, simulation, biomass growth, management policies",
    project_urls={
        "Bug Reports": "https://github.com/fulloaf/treemun/issues",
        "Source": "https://github.com/fulloaf/treemun",
    },
)


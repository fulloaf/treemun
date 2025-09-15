# treemun/setup.py

from setuptools import setup, find_packages
import os

# read the README for longer description
this_directory = os.path.abspath(os.path.dirname(__file__))
try:
    with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
        long_description = f.read()
except FileNotFoundError:
    long_description = "Growth, yield, and management simulator for Chilean plantation forests"

setup(
    name="treemun-sim",
    version="1.1.5", 
    author="Felipe Ulloa-Fierro",
    author_email="felipe.ulloa@utalca.cl", 
    description="Growth, yield, and management simulator for Chilean plantation forests",
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
        "pyomo>=6.0.0",  # new dependency for optimization
    ],
    include_package_data=True,
    package_data={
        "treemun_sim": ["data/*.csv"],
    },
    # optional dependencies for developtment and solvers 
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-cov>=2.0",
            "black>=21.0",
            "flake8>=3.8",
        ],
        "solvers": [
            "pulp>=2.0",  # include CBC (free solver)
        ],
        "solvers-extended": [
            "pulp>=2.0",  # CBC solver
            "cplex",      # CPLEX (requires license) 
        ],
        "complete": [
            "pulp>=2.0",
            "pytest>=6.0",
            "pytest-cov>=2.0",
            "black>=21.0",
            "flake8>=3.8",
        ],
    },
    # Uptdated metadata
    keywords="plantation forest, simulation, biomass growth, management policies, optimization, forest management",
    project_urls={
        "Bug Reports": "https://github.com/fulloaf/treemun/issues",
        "Source": "https://github.com/fulloaf/treemun",
        "Documentation": "https://github.com/fulloaf/treemun#readme",
    },
)
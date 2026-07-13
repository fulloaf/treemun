# treemun/setup.py

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="treemun-sim",
    version="1.4.0",
    author="Felipe Ulloa-Fierro",
    author_email="felipe.ulloa@utalca.cl",
    description=(
        "Open-source Python growth-and-yield simulator with MILP optimization "
        "and spatial GIS integration for Eucalyptus globulus and Pinus radiata "
        "plantations in south-central Chile"
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/fulloaf/treemun",
    packages=find_packages(),
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
        "spatial": [
            "geopandas>=0.10.0",  # for shapefile integration
            "shapely>=2.0.0",     # geometric operations
        ],
        "complete": [
            "pulp>=2.0",
            "pytest>=6.0",
            "pytest-cov>=2.0",
            "black>=21.0",
            "flake8>=3.8",
            "geopandas>=0.10.0",
            "shapely>=2.0.0",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering",
        "Topic :: Scientific/Engineering :: GIS",
        "Intended Audience :: Science/Research",
    ],
    keywords=[
        "forest management",
        "growth simulation",
        "MILP optimization",
        "GIS",
        "biomass",
        "carbon sequestration",
        "carbon stock",
        "Pinus radiata",
        "Eucalyptus globulus",
        "Chile",
    ],
    project_urls={
        "Bug Reports": "https://github.com/fulloaf/treemun/issues",
        "Source": "https://github.com/fulloaf/treemun",
        "Documentation": "https://github.com/fulloaf/treemun#readme",
    },
)
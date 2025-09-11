# Installation Guide

This guide provides detailed instructions for installing treemun and its dependencies.

## Requirements

### System Requirements
- Python 3.8 or higher
- Operating System: Windows, macOS, or Linux
- At least 100 MB of available disk space

### Python Dependencies
treemun automatically installs the following dependencies:
- `numpy >= 1.19.0`
- `pandas >= 1.2.0`

## Installation Methods

### Method 1: Install from PyPI (Recommended)

The easiest way to install treemun is using pip:

```bash
pip install treemun-sim
```

### Method 2: Install in a Virtual Environment

For isolated installations, use a virtual environment:

```bash
# Create virtual environment
python -m venv treemun_env

# Activate virtual environment
# On Windows:
treemun_env\Scripts\activate
# On macOS/Linux:
source treemun_env/bin/activate

# Install treemun
pip install treemun-sim
```

### Method 3: Install from Source

If you want to install from the GitHub repository:

```bash
git clone https://github.com/fulloa/treemun.git
cd treemun
pip install -e .
```

## Verify Installation

To verify that treemun is installed correctly:

```python
import treemun_sim as tm
print(tm.__version__)
print("TreeMun installed successfully!")
```

You should see the version number and confirmation message.

## Quick Test

Run a quick test to ensure everything works:

```python
import treemun_sim as tm

# Run a small simulation
forest, summary, final_biomass, estimated_biomass = tm.simular_bosque(
    num_rodales=5,
    horizonte=10
)

print(f"Test successful! Generated {len(forest)} stand-policy combinations.")
```

## Troubleshooting

### Common Issues

**Issue: ModuleNotFoundError**
```
ModuleNotFoundError: No module named 'treemun_sim'
```

**Solutions:**
1. Ensure you've installed the package: `pip install treemun-sim`
2. Check you're in the correct Python environment
3. Verify installation: `pip list | grep treemun`

**Issue: ImportError with dependencies**
```
ImportError: No module named 'numpy'
```

**Solutions:**
1. Update pip: `pip install --upgrade pip`
2. Install dependencies manually: `pip install numpy pandas`
3. Reinstall treemun: `pip uninstall treemun-sim && pip install treemun-sim`

**Issue: Permission errors on installation**

**Solutions:**
1. Use user installation: `pip install --user treemun-sim`
2. Use virtual environment (see Method 2 above)
3. On Linux/macOS, use sudo (not recommended): `sudo pip install treemun-sim`

### Getting Help

If you encounter issues not covered here:

1. Check the [GitHub Issues](https://github.com/fulloa/treemun/issues)
2. Create a new issue with:
   - Your operating system
   - Python version (`python --version`)
   - Error message (full traceback)
   - Steps to reproduce

## Updating TreeMun

To update to the latest version:

```bash
pip install --upgrade treemun-sim
```

To check your current version:

```python
import treemun_sim as tm
print(tm.__version__)
```

## Uninstalling

To remove treemun:

```bash
pip uninstall treemun-sim
```

## Development Installation

For developers who want to contribute:

```bash
# Clone repository
git clone https://github.com/fulloa/treemun.git
cd treemun

# Install in development mode
pip install -e .

# Install development dependencies
pip install pytest black flake8
```

This allows you to make changes to the code and see them immediately without reinstalling.

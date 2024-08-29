import importlib
from pathlib import Path

from .register import import_register as import_register

# Get the current directory (where __init__.py is located)
current_dir = Path(__file__).parent

# Iterate over all .py files in the current directory
for py_file in current_dir.glob("*.py"):
    # Skip __init__.py itself
    if py_file.name == "__init__.py":
        continue

    # Import the module by constructing the module name
    module_name = py_file.stem  # Get the file name without the extension

    # Import the module using importlib
    importlib.import_module(f".{module_name}", package=__package__)

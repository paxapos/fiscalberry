# src/main.py
import runpy
import os

# Set the current working directory to the script's directory
# This helps ensure relative paths within your app work correctly
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Run your actual main script
runpy.run_module('fiscalberry.gui', run_name='__main__')
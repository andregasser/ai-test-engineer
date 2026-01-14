import os

# Base workspace directory
WORKSPACE_DIR = os.path.join(os.getcwd(), "workspace")

# Ensure the workspace directory exists
os.makedirs(WORKSPACE_DIR, exist_ok=True)

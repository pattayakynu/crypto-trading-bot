import os
import sys

# Set API key for all tests BEFORE importing main
os.environ["WEB_API_KEY"] = "test-key"

# Ensure web/backend is in path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import os
import sys

# Add the parent directory to sys.path so that the awesometts module can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

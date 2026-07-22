import sys
import os

# Add root directory to path to resolve src modules correctly
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.agent import main

if __name__ == "__main__":
    main()

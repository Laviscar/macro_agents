import sys
import os

# Ensure the project root is on sys.path so that packages like `harness`,
# `agents`, etc. are importable without a separate install step.
sys.path.insert(0, os.path.dirname(__file__))

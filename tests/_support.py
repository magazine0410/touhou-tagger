"""Shared test setup; keeps the standalone source directory importable."""
import sys
from pathlib import Path


SOURCE_DIR = Path(__file__).resolve().parents[1] / "source"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

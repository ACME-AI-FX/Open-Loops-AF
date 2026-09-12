"""Install / repo root. Runtime files (config.json, state.json, state/) live here,
not next to the Python modules in openloops/.
"""
from pathlib import Path

PKG = Path(__file__).resolve().parent
ROOT = PKG.parent

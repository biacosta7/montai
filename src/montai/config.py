"""Caminhos e configurações centrais do projeto."""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
CATALOG_PATH = DATA_DIR / "catalog.json"

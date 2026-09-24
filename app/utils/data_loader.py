import json
from pathlib import Path
from typing import Dict, List, Any

# Корень проекта, где лежит папка data
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

def load_json(filename: str, subfolder: str = None) -> Dict[str, Any]:
    """Безопасная загрузка JSON-файла из папки data/ или data/{subfolder}/"""
    if subfolder:
        filepath = DATA_DIR / subfolder / filename
    else:
        filepath = DATA_DIR / filename
        
    if not filepath.exists():
        raise FileNotFoundError(f"Файл не найден: {filepath}")
        
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)
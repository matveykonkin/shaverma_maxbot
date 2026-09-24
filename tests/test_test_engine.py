# tests/test_test_engine.py
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.services.test_engine import select_test_questions

def test_select_sql_test():
    """Тест: выбор теста по навыкам Python и SQL"""
    test_data = select_test_questions(["python", "sql"])
    
    assert "error" not in test_data
    assert test_data["test_id"] == "python_sql_core"
    assert len(test_data["questions"]) > 0
    print(f"✅ Тест выбран: {test_data['test_name']}, вопросов: {len(test_data['questions'])}")

if __name__ == "__main__":
    test_select_sql_test()
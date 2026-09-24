import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.services.analyzer import extract_skills

def test_extract_python_and_sql():
    """Тест: текст упоминает Python и SQL"""
    text = "Требуется опыт работы с Python и SQL. Знание баз данных (PostgreSQL)."
    skills = extract_skills(text)
    
    skill_ids = [s["id"] for s in skills]
    assert "python" in skill_ids
    assert "sql" in skill_ids
    print("✅ Тест 1 пройден: Python и SQL распознаны")

def test_extract_git():
    """Тест: текст упоминает Git"""
    text = "Нужен опыт работы с Git, коммитами и ветками."
    skills = extract_skills(text)
    
    skill_ids = [s["id"] for s in skills]
    assert "git" in skill_ids
    print("✅ Тест 2 пройден: Git распознан")

def test_no_skills_found():
    """Тест: текст не содержит поддерживаемых навыков"""
    text = "Ищем менеджера по продажам и навыки работы с MS Office."
    skills = extract_skills(text)
    
    assert len(skills) == 0
    print("✅ Тест 3 пройден: Навыки не найдены корректно")

if __name__ == "__main__":
    test_extract_python_and_sql()
    test_extract_git()
    test_no_skills_found()
    print("\nВсе юнит-тесты анализатора пройдены!")
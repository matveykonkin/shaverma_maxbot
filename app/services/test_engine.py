# app/services/test_engine.py
import json
from pathlib import Path
from typing import List, Dict, Any

from app.utils.data_loader import DATA_DIR

def select_test_questions(detected_skill_ids: List[str]) -> Dict[str, Any]:
    """
    Автоматически ищет в папке data/tests/ тест,
    который полностью покрывает обнаруженные у пользователя навыки.
    """
    target_skills = set(detected_skill_ids)
    tests_folder = DATA_DIR / "tests"
    
    if not tests_folder.exists():
        return {"error": "Папка с тестами не найдена", "questions": []}

    # Проходим по каждому JSON-файлу в папке tests
    best_match = None
    max_covered = -1

    for test_file in tests_folder.glob("*.json"):
        try:
            with open(test_file, "r", encoding="utf-8") as f:
                test_data = json.load(f)
        except Exception:
            continue

        test_skills = set(test_data.get("covered_skills", []))
        
        # Сколько навыков из найденных у пользователя покрывает этот тест?
        covered_count = len(target_skills.intersection(test_skills))
        
        # Идеальный кандидат: покрывает ВСЕ навыки пользователя (target_skills <= test_skills)
        if target_skills.issubset(test_skills):
            # Если тест покрывает все навыки, проверяем, не лишний ли он (хочем минимализм)
            # Но для MVP подойдет первый найденный, покрывающий всё.
            best_match = test_data
            break 
        
        # Если не покрывает всё, запоминаем тот, что покрывает больше всего (fallback)
        if covered_count > max_covered:
            max_covered = covered_count
            best_match = test_data

    if best_match is None:
        return {"error": "Подходящие тесты не найдены в базе", "questions": []}

    # Проверяем, покрывает ли найденный тест все навыки
    test_skills = set(best_match.get("covered_skills", []))
    if not target_skills.issubset(test_skills):
        # Формируем понятную ошибку, какие именно навыки не хватает
        missing = target_skills - test_skills
        return {
            "error": f"Тест '{best_match.get('name')}' не покрывает навыки: {', '.join(missing)}",
            "questions": []
        }

    # Фильтруем вопросы только по тем навыкам, которые были найдены у пользователя
    filtered_questions = [
        q for q in best_match["questions"] 
        if q["skill_id"] in target_skills
    ]

    return {
        "test_id": best_match["id"],
        "test_name": best_match["name"],
        "questions": filtered_questions
    }
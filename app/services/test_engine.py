"""Выбор и проверка готовых тестов из существующего каталога данных."""

import json
import logging

from app.utils.data_loader import DATA_DIR, load_json

log = logging.getLogger(__name__)


def validate_questions(questions):
    """Отбрасывает повреждённый банк до выдачи вопроса или расчёта результата."""
    if not isinstance(questions, list) or not 1 <= len(questions) <= 50:
        raise ValueError("Тест должен содержать от 1 до 50 вопросов")
    seen = set()
    for question in questions:
        if not isinstance(question, dict):
            raise ValueError("Некорректный вопрос")
        for field in ("id", "skill_id", "prompt", "explanation", "correct_option_id"):
            if not isinstance(question.get(field), str) or not question[field].strip():
                raise ValueError("Отсутствует обязательное поле вопроса")
        if question["id"] in seen:
            raise ValueError("Повторяющийся вопрос")
        seen.add(question["id"])
        options = question.get("options")
        if not isinstance(options, list) or not 2 <= len(options) <= 10:
            raise ValueError("Некорректные варианты ответа")
        ids = []
        for option in options:
            if not isinstance(option, dict) or any(
                not isinstance(option.get(field), str) or not option[field].strip()
                for field in ("id", "text")
            ):
                raise ValueError("Некорректный вариант ответа")
            ids.append(option["id"])
        if len({value.casefold() for value in ids}) != len(ids):
            raise ValueError("Повторяющиеся варианты ответа")
        if question["correct_option_id"] not in ids:
            raise ValueError("Правильного ответа нет среди вариантов")
        if len(question["prompt"]) + sum(len(o["text"]) + len(o["id"]) for o in options) > 3500:
            raise ValueError("Вопрос не помещается в сообщение")


def select_test_questions(detected_skill_ids):
    error = {"error": "Нет подходящего готового теста для этих навыков", "questions": []}
    if not isinstance(detected_skill_ids, (list, tuple)) or not detected_skill_ids:
        return error
    if any(not isinstance(skill, str) or not skill for skill in detected_skill_ids):
        return error
    target_skills = set(detected_skill_ids)
    # Диагностика предназначена для Python/backend, а не для любого упоминания SQL.
    if "python" not in target_skills or len(target_skills) < 2:
        return error
    try:
        known_skills = {skill["id"] for skill in load_json("skills.json")["skills"]}
        if not target_skills <= known_skills:
            return error
        candidates = []
        for test_file in sorted((DATA_DIR / "tests").glob("*.json")):
            try:
                with test_file.open(encoding="utf-8") as stream:
                    test_data = json.load(stream)
                if not isinstance(test_data, dict):
                    raise ValueError("Некорректный тест")
                if any(not isinstance(test_data.get(key), str) or not test_data[key].strip()
                       for key in ("id", "name")):
                    raise ValueError("У теста нет названия или идентификатора")
                covered = test_data.get("covered_skills")
                if not isinstance(covered, list) or not covered or any(
                    not isinstance(skill, str) or skill not in known_skills for skill in covered
                ):
                    raise ValueError("Некорректные навыки теста")
                validate_questions(test_data.get("questions"))
                if {q["skill_id"] for q in test_data["questions"]} != set(covered):
                    raise ValueError("Заявленное покрытие отличается от вопросов")
                if target_skills <= set(covered):
                    candidates.append(test_data)
            except (OSError, ValueError, TypeError, KeyError):
                log.warning("Пропущен некорректный файл теста: %s", test_file.name)
        if not candidates:
            return error
        best = min(candidates, key=lambda test: (
            len(set(test["covered_skills"]) - target_skills), len(test["questions"]), test["id"]
        ))
        return {
            "test_id": best["id"],
            "test_name": best["name"],
            "questions": [q for q in best["questions"] if q["skill_id"] in target_skills],
        }
    except (OSError, ValueError, TypeError, KeyError):
        log.warning("Не удалось загрузить справочник или каталог тестов")
        return error

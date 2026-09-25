"""Детерминированная оценка только полного набора допустимых ответов."""

from app.services.test_engine import validate_questions
from app.utils.data_loader import load_json

_rules = load_json("evaluation_rules.json")


def validate_answers(answers, questions, *, complete=True):
    validate_questions(questions)
    if not isinstance(answers, list):
        raise ValueError("Ответы должны быть списком")
    q_map = {q["id"]: q for q in questions}
    seen = set()
    for answer in answers:
        if not isinstance(answer, dict):
            raise ValueError("Некорректный ответ")
        q_id = answer.get("question_id")
        option_id = answer.get("selected_option_id")
        if not isinstance(q_id, str) or q_id not in q_map or q_id in seen:
            raise ValueError("Неизвестный или повторяющийся вопрос")
        if not isinstance(option_id, str) or option_id not in {
            option["id"] for option in q_map[q_id]["options"]
        }:
            raise ValueError("Недопустимый вариант ответа")
        seen.add(q_id)
    if complete and seen != set(q_map):
        raise ValueError("Тест не завершён")


def calculate_score(answers, questions):
    validate_answers(answers, questions)
    q_map = {q["id"]: q for q in questions}
    skill_stats = {}
    wrong_question_ids = []
    correct_count = 0
    for answer in answers:
        question = q_map[answer["question_id"]]
        stats = skill_stats.setdefault(question["skill_id"], {"correct": 0, "total": 0})
        stats["total"] += 1
        # Не доверяем переданному is_correct: всегда сверяем с ключом банка.
        if answer["selected_option_id"] == question["correct_option_id"]:
            correct_count += 1
            stats["correct"] += 1
        else:
            wrong_question_ids.append(question["id"])
    total_count = len(questions)
    ready_threshold = _rules["decision_rules"]["ready"]["overall_min_percent"]
    skill_threshold = _rules["decision_rules"]["ready"]["required_skill_min_percent"]
    is_ready = correct_count * 100 >= total_count * ready_threshold and all(
        stats["correct"] * 100 >= stats["total"] * skill_threshold
        for stats in skill_stats.values()
    )

    def percent(correct, total):
        # Целочисленное округление половины вверх; решение принято до округления.
        return (correct * 200 + total) // (2 * total)

    return {
        "total_score": f"{correct_count}/{total_count}",
        "overall_percent": percent(correct_count, total_count),
        "skill_scores": {skill: percent(stats["correct"], stats["total"])
                         for skill, stats in skill_stats.items()},
        "is_ready": is_ready,
        "wrong_question_ids": wrong_question_ids,
        "thresholds_used": {"overall": ready_threshold, "skill": skill_threshold},
    }

import json
from pathlib import Path
from typing import List, Dict

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LEARNING_MATERIALS_FILE = DATA_DIR / "learning_materials.json"

with open(LEARNING_MATERIALS_FILE, "r", encoding="utf-8") as f:
    learning_materials = json.load(f)

def get_learning_materials(question_id: str) -> List[Dict]:
    """Возвращает материалы, связанные с вопросом."""
    result = []

    for item in learning_materials.get("items", []):
        for link in item.get("links", []):
            if question_id in link.get("question_ids", []):
                result.append(link)

    return result

def build_feedback(wrong_ids: List[str], questions: List[Dict], user_answers: List[Dict]) -> str:
    """
    Формирует подробный фидбэк:
    вопрос -> ответ пользователя -> правильный ответ -> объяснение -> материалы для повторения.
    """
    if not wrong_ids:
        return "Все ответы верны. Результат относится только к проверенным темам."

    q_map = {q["id"]: q for q in questions}
    answers_map = {ans["question_id"]: ans for ans in user_answers}

    feedback_lines = ["Вот что нужно повторить:\n"]

    for q_id in wrong_ids:
        question = q_map.get(q_id)
        user_ans = answers_map.get(q_id)

        if not question or not user_ans:
            continue

        correct_option = next(
            (
                opt
                for opt in question["options"]
                if opt["id"] == question["correct_option_id"]
            ),
            None
        )

        correct_text = (
            correct_option["text"]
            if correct_option
            else "Не удалось определить правильный ответ"
        )

        feedback_lines.append(f"Вопрос: {question['prompt']}")
        feedback_lines.append(
            f"Твой ответ: {user_ans['selected_option_text']}"
        )
        feedback_lines.append(f"Правильный ответ: {correct_text}")
        feedback_lines.append(
            f"Почему это так: "
            f"{question.get('explanation', 'Объяснение отсутствует.')}"
        )

        materials = get_learning_materials(q_id)

        if materials:
            feedback_lines.append("📚 Что повторить:")

            for material in materials:
                label = material.get("label", "Материал для повторения")
                url = material.get("url")

                if url:
                    feedback_lines.append(f"   • {label}: {url}")
                else:
                    feedback_lines.append(f"   • {label}")

                sections = material.get("read_sections")
                if sections:
                    feedback_lines.append(f"     Разделы: {sections}")

        feedback_lines.append("")

    return "\n".join(feedback_lines)
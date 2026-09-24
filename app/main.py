"""
MAX-бот для проверки готовности к стажировкам.
Использует rule-based анализатор и тест-движок.
"""

import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.analyzer import extract_skills
from app.services.test_engine import select_test_questions
from app.services.scoring import calculate_score
from app.services.feedback import build_feedback

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "https://platform-api2.max.ru")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в .env")

HEADERS = {
    "Authorization": BOT_TOKEN,
}

# Простое хранилище состояния в памяти
user_sessions = {}


def get_updates(marker=None):
    params = {
        "timeout": 30,
        "types": "message_created",
    }

    if marker is not None:
        params["marker"] = marker

    response = requests.get(
        f"{BASE_URL}/updates",
        headers=HEADERS,
        params=params,
        timeout=40,
    )

    response.raise_for_status()
    return response.json()


def send_message(user_id, text):
    response = requests.post(
        f"{BASE_URL}/messages",
        headers=HEADERS,
        params={"user_id": user_id},
        json={"text": text},
        timeout=10,
    )

    response.raise_for_status()
    return response


def analyze_internship(user_id: int, text: str) -> str:
    """Анализирует описание стажировки и возвращает результат."""
    skills = extract_skills(text)
    
    if not skills:
        return (
            "Не нашёл в описании поддерживаемых навыков (Python, SQL, Git, HTTP). "
            "Пожалуйста, убедитесь, что текст содержит технические требования."
        )
    
    # Формируем ответ о найденных навыках
    skills_text = ", ".join([f"{s['name']}" for s in skills])
    skill_ids = [s["id"] for s in skills]
    
    # Подбираем тест
    test_data = select_test_questions(skill_ids)
    
    if "error" in test_data:
        return f"К сожалению, по навыкам ({skills_text}) нет готового теста."
    
    # Сохраняем сессию (теперь user_id доступен)
    user_sessions[user_id] = {
        "test_data": test_data,
        "skills": skills,
        "current_question": 0,
        "answers": []
    }
    
    msg = (
        f"В стажировке важны навыки: **{skills_text}**.\n\n"
        f"Я подготовил короткую проверку: **{test_data['test_name']}** "
        f"(вопросов: {len(test_data['questions'])}).\n\n"
        "Готов пройти тест?"
    )
    
    return msg


def process_user_message(user_id: int, text: str) -> str:
    """Обрабатывает сообщение пользователя в зависимости от состояния."""
    
    # Проверяем, есть ли активная сессия теста
    session = user_sessions.get(user_id)
    
    if session and "test_data" in session:
        # Пользователь проходит тест
        return handle_test_response(user_id, text)
    
    # Если сессии нет - анализируем как описание стажировки
    if len(text) < 30:
        return "Пришли описание стажировки. Я выделю ключевые requirements и проверю знания по ним коротким тестом."
    
    return analyze_internship(user_id, text)


def handle_test_response(user_id: int, text: str) -> str:
    """Обрабатывает ответ на вопрос теста."""
    session = user_sessions[user_id]
    test_data = session["test_data"]
    questions = test_data["questions"]
    current_idx = session["current_question"]
    
    if current_idx >= len(questions):
        return "Тест уже завершен. Пришли новое описание стажировки."
    
    current_question = questions[current_idx]
    
    # Проверяем, что пользователь выбрал вариант ответа
    try:
        selected_option_id = text.strip().lower()
        # Ищем подходящий вариант
        option = next(
            (opt for opt in current_question["options"] 
             if opt["id"].lower() == selected_option_id),
            None
        )
        
        if not option:
            # Показываем доступные варианты
            options_text = "\n".join([
                f"{opt['id']}: {opt['text']}" 
                for opt in current_question["options"]
            ])
            if not option:
                # Показываем вопрос и варианты ответа, если пользователь ввёл не то
                question_text = current_question.get('prompt', 'Вопрос:')
                options_text = "\n".join([
                    f"{opt['id']}: {opt['text']}" 
                    for opt in current_question["options"]
                ])
                return f"{question_text}\n\nВыбери вариант:\n{options_text}"
        
        # Записываем ответ
        is_correct = option["id"] == current_question["correct_option_id"]
        session["answers"].append({
            "question_id": current_question["id"],
            "selected_option_id": option["id"],
            "is_correct": is_correct
        })
        
        session["current_question"] += 1
        
        # Переходим к следующему вопросу или завершаем тест
        if session["current_question"] < len(questions):
            next_q = questions[session["current_question"]]
            options_text = "\n".join([
                f"{opt['id']}: {opt['text']}" 
                for opt in next_q["options"]
            ])
            return f"Следующий вопрос:\n{next_q['prompt']}\n\n{options_text}"
        else:
            # Завершаем тест и оцениваем
            result = calculate_score(session["answers"], questions)
            feedback = build_feedback(
                result["wrong_question_ids"], 
                questions
            )
            
            # Формируем итоговый ответ
            status = "✅ Готов к отклику" if result["is_ready"] else "⚠️ Нужно подтянуть"
            
            final_msg = (
                f"Тест завершен!\n\n"
                f"Общий результат: {result['total_score']} ({result['overall_percent']}%)\n\n"
                f"По навыкам:\n" + 
                "\n".join([
                    f"- {skill}: {score}%" 
                    for skill, score in result["skill_scores"].items()
                ]) +
                f"\n\n{status}\n\n{feedback}"
            )
            
            # Очищаем сессию
            del user_sessions[user_id]
            return final_msg
            
    except Exception as e:
        return f"Ошибка при обработке ответа: {e}"


def main():
    print("MAX-бот для проверки стажировок запущен!")

    marker = None

    while True:
        try:
            data = get_updates(marker)

            marker = data.get("marker")

            for update in data.get("updates", []):
                if update.get("update_type") != "message_created":
                    continue

                message = update.get("message", {})
                sender = message.get("sender", {})

                user_id = sender.get("user_id")
                text = message.get("body", {}).get("text", "")

                if user_id is None:
                    continue

                print(f"Получено сообщение от {user_id}: {text[:50]}...")

                # Обрабатываем сообщение
                response_text = process_user_message(user_id, text)
                
                # Отправляем ответ
                send_message(user_id, response_text)
                print(f"Ответ отправлен пользователю {user_id}")

        except Exception as error:
            print(f"Ошибка: {error}")
            time.sleep(5)


if __name__ == "__main__":
    main()
# app/handlers/internship.py
from app.services.analyzer import extract_skills
from app.services.test_engine import select_test_questions
from app.max_client import send_message

async def handle_internship_text(user_id: int, text: str):
    """
    Обрабатывает текст стажировки, отправленный пользователем.
    """
    # 1. Извлекаем навыки
    skills = extract_skills(text)
    
    if not skills:
        await send_message(
            user_id, 
            "Не нашёл в описании поддерживаемых навыков (Python, SQL, Git, HTTP). "
            "Пожалуйста, убедитесь, что текст содержит технические требования."
        )
        return
        
    # 2. Формируем красивый список навыков для пользователя
    skills_text = ", ".join([f"{s['name']}" for s in skills])
    skill_ids = [s["id"] for s in skills]
    
    # 3. Подбираем тест
    test_data = select_test_questions(skill_ids)
    
    if "error" in test_data:
        await send_message(user_id, "К сожалению, по этим навыкам нет готового теста.")
        return
        
    # 4. Отправляем приглашение на тест
    msg = (
        f"В стажировке важны навыки: **{skills_text}**.\n\n"
        f"Я подготовил короткую проверку: **{test_data['test_name']}** "
        f"(вопросов: {len(test_data['questions'])}).\n\n"
        "Хочешь пройти её?"
    )
    
    # Здесь можно добавить inline-кнопки "Да, начать" / "Нет, спасибо"
    await send_message(user_id, msg)
def build_feedback(wrong_ids: List[str], questions: List[Dict], user_answers: List[Dict]) -> str:
    """
    Формирует подробный фидбэк: вопрос -> ответ пользователя -> правильный ответ -> объяснение.
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
            (opt for opt in question["options"] 
             if opt["id"] == question["correct_option_id"]),
            None
        )
        correct_text = correct_option["text"] if correct_option else "Unknown correct answer"
        
        feedback_lines.append(f"   Вопрос: {question['prompt']}")
        feedback_lines.append(f"       Твой ответ: {user_ans['selected_option_text']}")
        feedback_lines.append(f"       Правильный ответ: {correct_text}")
        feedback_lines.append(f"       Почему это так: {question.get('explanation', 'Обратитесь к учебнику')}")
        feedback_lines.append("") # Пустая строка для читаемости
        
    return "\n".join(feedback_lines)

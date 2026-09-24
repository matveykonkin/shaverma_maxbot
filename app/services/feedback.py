def build_feedback(wrong_ids: List[str], questions: List[Dict]) -> str:
    """
    Собирает понятный текст обратной связи.
    Использует поля 'explanation' из вопросов, которые были в JSON-тесте.
    """
    q_map = {q["id"]: q for q in questions}
    
    feedback_lines = ["**Вот что нужно повторить:**\n"]
    
    for q_id in wrong_ids:
        q = q_map.get(q_id)
        if not q:
            continue
        feedback_lines.append(f"*   **Вопрос:** {q['prompt']}")
        feedback_lines.append(f"*   *Почему это так:* {q.get('explanation', 'Обратитесь к учебнику')}")
        feedback_lines.append("")
        
    return "\n".join(feedback_lines)
from typing import Dict, List
from app.utils.data_loader import load_json

# Загружаем правила оценки один раз
_rules = load_json("evaluation_rules.json")

def calculate_score(answers: List[Dict], questions: List[Dict]) -> Dict:
    """
    Считает результаты теста.
    answers: [{"question_id": "ps01", "selected_option_id": "c"}, ...]
    questions: Список вопросов из теста
    """
    # Создадим словарь вопроса для быстрого поиска
    q_map = {q["id"]: q for q in questions}
    
    correct_count = 0
    total_count = len(answers)
    skill_stats = {} # { "python": {"correct": 0, "total": 0}, ... }
    
    wrong_question_ids = []
    
    for ans in answers:
        q_id = ans.get("question_id")
        selected_opt = ans.get("selected_option_id")
        
        question = q_map.get(q_id)
        if not question:
            continue # Пропускаем мусор
            
        skill_id = question["skill_id"]
        if skill_id not in skill_stats:
            skill_stats[skill_id] = {"correct": 0, "total": 0}
            
        skill_stats[skill_id]["total"] += 1
        
        # Проверка правильности ответа
        correct_opt = question.get("correct_option_id")
        if selected_opt == correct_opt:
            correct_count += 1
            skill_stats[skill_id]["correct"] += 1
        else:
            wrong_question_ids.append(q_id)
            
    # Рассчитываем проценты согласно evaluation_rules.json
    # rule: overall_percent = correct / total * 100
    overall_percent = (correct_count / total_count * 100) if total_count > 0 else 0
    
    # Рассчитываем процент по каждому навыку
    skill_percents = {}
    for s_id, stats in skill_stats.items():
        skill_percents[s_id] = round((stats["correct"] / stats["total"]) * 100)
        
    # Применяем decision_rules из JSON
    ready_threshold = _rules["decision_rules"]["ready"]["overall_min_percent"] # 70%
    skill_threshold = _rules["decision_rules"]["ready"]["required_skill_min_percent"] # 60%
    
    is_ready = overall_percent >= ready_threshold and all(p >= skill_threshold for p in skill_percents.values())
    
    return {
        "total_score": f"{correct_count}/{total_count}",
        "overall_percent": round(overall_percent),
        "skill_scores": skill_percents,
        "is_ready": is_ready,
        "wrong_question_ids": wrong_question_ids,
        "thresholds_used": {
            "overall": ready_threshold,
            "skill": skill_threshold
        }
    }
import re
from typing import List, Dict
from app.utils.data_loader import load_json

_skills_taxonomy = None

def get_taxonomy():
    global _skills_taxonomy
    if _skills_taxonomy is None:
        _skills_taxonomy = load_json("skills.json")
    return _skills_taxonomy

def extract_skills(text: str) -> List[Dict]:
    """
    Извлекает навыки из текста стажировки на основе skills.json.
    Возвращает список словарей: [{"id": "python", "name": "Python", "weight": 0.8}, ...]
    """
    taxonomy = get_taxonomy()
    skills_list = taxonomy.get("skills", [])
    
    text_lower = text.lower()
    detected_skills = []
    
    for skill in skills_list:
        score = 0
        matched_terms = []
        
        for alias in skill.get("aliases", []):
            pattern = re.escape(alias.lower())
            if re.search(rf"\b{pattern}\b", text_lower):
                score += 2
                matched_terms.append(alias)
                
        for term in skill.get("contextual_terms", []):
            pattern = re.escape(term.lower())
            if re.search(rf"\b{pattern}\b", text_lower):
                score += 1
                matched_terms.append(term)
                
        if score > 0:
            weight = min(score / 10.0, 1.0)
            if weight < 0.2:
                weight = 0.2 # Минимальный порог уверенности
                
            detected_skills.append({
                "id": skill["id"],
                "name": skill["name"],
                "weight": round(weight, 2),
                "matched_terms": matched_terms
            })
            
    detected_skills.sort(key=lambda x: x["weight"], reverse=True)
    return detected_skills
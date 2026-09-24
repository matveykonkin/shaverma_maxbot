# tests/test_scoring.py
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.services.test_engine import select_test_questions
from app.services.scoring import calculate_score

def test_scoring_perfect_result():
    """Тест: идеальный результат (все ответы верны)"""
    test_data = select_test_questions(["python", "sql"])
    questions = test_data["questions"]
    
    # Имитируем правильные ответы
    mock_answers = [
        {"question_id": q["id"], "selected_option_id": q["correct_option_id"]}
        for q in questions
    ]
    
    result = calculate_score(mock_answers, questions)
    
    assert result["overall_percent"] == 100
    assert result["is_ready"] == True
    print(f"✅ Идеальный результат: {result['total_score']} ({result['overall_percent']}%)")

def test_scoring_low_result():
    """Тест: низкий результат (все ответы неверны)"""
    test_data = select_test_questions(["python", "sql"])
    questions = test_data["questions"]
    
    # Имитируем неправильные ответы (выбираем не те опции)
    mock_answers = []
    for q in questions:
        wrong_opts = [opt["id"] for opt in q["options"] if opt["id"] != q["correct_option_id"]]
        mock_answers.append({
            "question_id": q["id"],
            "selected_option_id": wrong_opts[0] if wrong_opts else "none"
        })
        
    result = calculate_score(mock_answers, questions)
    
    assert result["overall_percent"] == 0
    assert result["is_ready"] == False
    print(f"✅ Низкий результат: {result['total_score']} ({result['overall_percent']}%)")

if __name__ == "__main__":
    test_scoring_perfect_result()
    test_scoring_low_result()
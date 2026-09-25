import json

import pytest

from app.parsing import (
    MAX_INPUT_LENGTH, UserInputError, normalize_text, parse_option,
    unsupported_direction, valid_user_id, validate_description,
)
from app.services.analyzer import extract_skills
from app.services import test_engine
from app.services.scoring import calculate_score
from app.utils.data_loader import load_json


@pytest.mark.parametrize("value", [None, False, 15, {}, [], b"Python", "", " \n\t ",
                                  "\u200b\ufeff\u2060", "text\x00", "text\x1b", "\ud800",
                                  "x" * (MAX_INPUT_LENGTH + 1)])
def test_invalid_text_is_rejected(value):
    with pytest.raises(UserInputError):
        normalize_text(value)


def test_unicode_and_whitespace_normalization():
    assert normalize_text(" \ufeffＰｙｔｈｏｎ\u200b\r\n SQL\u00a0 ") == "Python\r\n SQL"


def test_input_length_boundary():
    assert len(normalize_text("x" * MAX_INPUT_LENGTH)) == MAX_INPUT_LENGTH
    # NFKC может увеличивать длину: ограничение проверяется и после нормализации.
    with pytest.raises(UserInputError):
        normalize_text("\ufb03" * 3000)


@pytest.mark.parametrize("value", [True, False, None, 0, -1, 1.5, "123", [], {}, 2**63])
def test_bad_user_ids(value):
    assert not valid_user_id(value)


@pytest.mark.parametrize("value", [1, 2**63 - 1])
def test_valid_user_ids(value):
    assert valid_user_id(value)


@pytest.mark.parametrize("value", [
    "Python SQL", "!" * 100, "123456 " * 20, "🙂 " * 30,
    "https://hh.ru/vacancy/123456789", "hh.ru/vacancy/123456789",
    "Вот вакансия: https://example.com/python/sql/http",
    "https://first.ru/python\nhttps://second.ru/git",
    "[Стажировка](https://example.com/python/backend)",
])
def test_description_needs_words_not_links_or_padding(value):
    with pytest.raises(UserInputError):
        validate_description(value)


def test_description_with_source_link_is_accepted():
    text = "Python backend стажировка: нужны SQL и Git. Источник https://hh.ru/vacancy/123"
    assert validate_description(text) == text


@pytest.mark.parametrize("value", [None, {}, [], 42, "", "https://python.org/sql/git",
                                  "GitHub GitLab FastAPI PostgreSQL векторные базы данных"])
def test_invalid_or_context_only_text_does_not_invent_skills(value):
    assert extract_skills(value) == []


def test_url_scheme_does_not_invent_http_requirement():
    ids = {skill["id"] for skill in extract_skills("Требуются Python и SQL: https://example.com/")}
    assert ids == {"python", "sql"}


@pytest.mark.parametrize("text", [
    "Ищем frontend разработчика, нужен Python и SQL для инструментов",
    "Стажер NLP: опыт Python, REST API, LLM",
    "Data analyst: Python SQL Git", "QA стажёр: Python и SQL",
])
def test_explicit_other_direction(text):
    assert unsupported_direction(text)


def test_backend_with_ai_tasks_is_supported():
    assert not unsupported_direction("Backend разработчик на Python для AI: SQL, REST API")


@pytest.fixture
def options():
    return [{"id": letter, "text": letter.upper()} for letter in "abcd"]


@pytest.mark.parametrize("text, expected", [("a", "a"), (" A ", "a"), ("B", "b"),
                                            ("1", "a"), ("4", "d"), ("\u200bc", "c")])
def test_one_option_only(text, expected, options):
    assert parse_option(text, options) == expected


@pytest.mark.parametrize("text", ["a b", "a,b", "1,2", "0", "5", "-1", "1.0", "01",
                                  "выбираю a", "а", "да", "/skip", "", None, ["a"]])
def test_ambiguous_or_unknown_option(text, options):
    with pytest.raises(UserInputError):
        parse_option(text, options)


@pytest.mark.parametrize("skills", [None, "python", [], {}, [None], [42], [["python"]],
                                    ["java"], ["sql"], ["python"], ["python", "unknown"]])
def test_unsupported_skill_sets(skills):
    result = test_engine.select_test_questions(skills)
    assert result["questions"] == []
    assert "error" in result


@pytest.mark.parametrize("skills, expected", [
    (["python", "sql"], "python_sql_core"),
    (["python", "sql", "sql"], "python_sql_core"),
    (["python", "git"], "python_web_git"),
    (["python", "rest_api"], "python_web_git"),
    (["python", "sql", "git"], "python_backend_full"),
])
def test_selection_is_deterministic_and_covers_skills(skills, expected):
    result = test_engine.select_test_questions(skills)
    assert result["test_id"] == expected
    assert {q["skill_id"] for q in result["questions"]} == set(skills)


def test_broken_test_file_is_skipped(tmp_path, monkeypatch):
    directory = tmp_path / "tests"
    directory.mkdir()
    (directory / "broken.json").write_text("{", encoding="utf-8")
    (directory / "wrong_shape.json").write_text("[]", encoding="utf-8")
    good = load_json("python_sql_core.json", "tests")
    (directory / "valid.json").write_text(json.dumps(good), encoding="utf-8")
    monkeypatch.setattr(test_engine, "DATA_DIR", tmp_path)
    assert test_engine.select_test_questions(["python", "sql"])["test_id"] == good["id"]


def test_empty_catalog_has_no_test(tmp_path, monkeypatch):
    monkeypatch.setattr(test_engine, "DATA_DIR", tmp_path)
    assert "error" in test_engine.select_test_questions(["python", "sql"])


@pytest.fixture
def questions():
    return load_json("python_sql_core.json", "tests")["questions"]


def correct_answers(questions):
    return [{"question_id": q["id"], "selected_option_id": q["correct_option_id"]} for q in questions]


@pytest.mark.parametrize("invalid", [None, {}, "a", [], [None], [1], [{"question_id": []}],
                                     [{"question_id": "unknown", "selected_option_id": "a"}]])
def test_malformed_answers_cannot_be_scored(questions, invalid):
    with pytest.raises(ValueError):
        calculate_score(invalid, questions)


def test_incomplete_attempt_cannot_look_ready(questions):
    with pytest.raises(ValueError, match="не завершён"):
        calculate_score(correct_answers(questions)[:1], questions)


def test_duplicate_answers_cannot_inflate_score(questions):
    answers = correct_answers(questions)
    answers[-1] = answers[0]
    with pytest.raises(ValueError):
        calculate_score(answers, questions)


@pytest.mark.parametrize("option", [None, [], True, "x", "a,b"])
def test_nonexistent_option_is_not_a_wrong_knowledge_answer(questions, option):
    answers = correct_answers(questions)
    answers[0]["selected_option_id"] = option
    with pytest.raises(ValueError):
        calculate_score(answers, questions)


def test_precalculated_correctness_is_not_trusted(questions):
    answers = correct_answers(questions)
    for answer in answers:
        answer["is_correct"] = False
    assert calculate_score(answers, questions)["overall_percent"] == 100


@pytest.mark.parametrize("case", load_json("demo_cases.json")["cases"], ids=lambda case: case["id"])
def test_saved_reference_results(case):
    questions = load_json(case["test_id"] + ".json", "tests")["questions"]
    answers = [{"question_id": key, "selected_option_id": value} for key, value in case["answers"].items()]
    result = calculate_score(answers, questions)
    expected = case["expected_result"]
    assert result["overall_percent"] == expected["overall_percent"]
    assert result["is_ready"] == (expected["decision"] == "ready")
    assert result["total_score"] == f"{expected['correct_answers']}/{expected['total_questions']}"
    assert result["wrong_question_ids"] == expected["incorrect_question_ids"]


def test_skill_threshold_is_compared_before_rounding(questions, monkeypatch):
    # 25/42 округляется до 60, но не достигает 60. Временно снижаем
    # общий порог, чтобы он не скрывал ошибку сравнения по навыку.
    from copy import deepcopy
    from app.services import scoring
    rules = deepcopy(scoring._rules)
    rules["decision_rules"]["ready"]["overall_min_percent"] = 60
    monkeypatch.setattr(scoring, "_rules", rules)
    expanded = []
    for index in range(50):
        question = deepcopy(questions[0])
        question["id"] = f"q{index}"
        question["skill_id"] = "python" if index < 42 else "sql"
        expanded.append(question)
    answers = correct_answers(expanded)
    for index in range(25, 42):
        answers[index]["selected_option_id"] = "a"
    result = calculate_score(answers, expanded)
    assert result["overall_percent"] >= 60
    assert result["skill_scores"]["python"] == 60
    assert not result["is_ready"]


@pytest.mark.parametrize("change", ["empty", "duplicate", "bad_key", "bad_options", "missing_prompt"])
def test_invalid_bank_is_rejected(questions, change):
    if change == "empty":
        questions = []
    elif change == "duplicate":
        questions.append(questions[0])
    elif change == "bad_key":
        questions[0]["correct_option_id"] = "unknown"
    elif change == "bad_options":
        questions[0]["options"] = None
    else:
        questions[0]["prompt"] = ""
    with pytest.raises(ValueError):
        test_engine.validate_questions(questions)

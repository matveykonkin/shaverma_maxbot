from copy import deepcopy
from unittest.mock import Mock

import pytest
import requests

from app import main as bot

DESCRIPTION = "Ищем стажёра Python backend: нужны SQL, Git и HTTP REST API."


@pytest.fixture(autouse=True)
def isolated_bot(monkeypatch):
    bot.user_sessions.clear()
    bot._processed_messages.clear()
    bot._send_times.clear()
    # Любая случайная реальная отправка во время теста считается ошибкой.
    monkeypatch.setattr(bot.requests, "get", Mock(side_effect=AssertionError("No real HTTP")))
    monkeypatch.setattr(bot.requests, "post", Mock(side_effect=AssertionError("No real HTTP")))
    yield
    bot.user_sessions.clear()
    bot._processed_messages.clear()
    bot._send_times.clear()


def begin(user_id=1):
    assert "Напиши «да»" in bot.process_user_message(user_id, DESCRIPTION)
    reply = bot.process_user_message(user_id, "да")
    assert "Вопрос 1/" in reply
    return bot.user_sessions[user_id]


def event(mid="m1", text=DESCRIPTION, user_id=1, timestamp=1000):
    return {
        "update_type": "message_created",
        "message": {
            "sender": {"user_id": user_id, "is_bot": False},
            "recipient": {"chat_type": "dialog"},
            "timestamp": timestamp,
            "body": {"mid": mid, "text": text},
        },
    }


def sender_mock(monkeypatch):
    send = Mock(return_value=Mock(json=lambda: {"message": {"timestamp": 2000}}))
    monkeypatch.setattr(bot, "send_message", send)
    return send


@pytest.mark.parametrize("text", [None, [], {}, 42, "", " \n ", "\u200b", "https://hh.ru/vacancy/123",
                                   "Python SQL", "🙂" * 50, "x" * 8001, "SQL Git Docker: нужен опыт разработки приложений"])
def test_invalid_description_does_not_start_test(text):
    reply = bot.process_user_message(1, text)
    assert isinstance(reply, str) and reply
    assert 1 not in bot.user_sessions


def test_confirmation_is_not_an_answer():
    bot.process_user_message(1, DESCRIPTION)
    before = deepcopy(bot.user_sessions[1])
    reply = bot.process_user_message(1, "a")
    assert "подтверди" in reply
    assert bot.user_sessions[1] == before
    bot.process_user_message(1, "да")
    assert bot.user_sessions[1]["answers"] == []
    assert bot.user_sessions[1]["current_question"] == 0


@pytest.mark.parametrize("text", [None, "", {}, "a,b", "5", "0", "а", "да", DESCRIPTION,
                                   "x" * 8001, "/unknown", "/start extra", "../../.env"])
def test_invalid_answer_preserves_progress(text):
    begin()
    before = deepcopy(bot.user_sessions[1])
    reply = bot.process_user_message(1, text)
    assert isinstance(reply, str) and reply
    assert bot.user_sessions[1] == before


@pytest.mark.parametrize("command", ["/help", "/start", "/continue", "/result"])
def test_non_destructive_commands_during_test(command):
    begin()
    bot.process_user_message(1, "a")
    before = deepcopy(bot.user_sessions[1])
    assert bot.process_user_message(1, command)
    assert bot.user_sessions[1] == before


def test_postpone_keeps_prepared_test():
    bot.process_user_message(1, DESCRIPTION)
    before = deepcopy(bot.user_sessions[1])
    assert "Вернуться" in bot.process_user_message(1, "не сейчас")
    assert bot.user_sessions[1] == before
    assert "да" in bot.process_user_message(1, "/continue")


def test_restart_requires_confirmation_and_no_restores_progress():
    begin()
    bot.process_user_message(1, "a")
    before = deepcopy(bot.user_sessions[1])
    assert "очистить" in bot.process_user_message(1, "/restart")
    assert bot.user_sessions[1]["answers"] == before["answers"]
    bot.process_user_message(1, "b")
    assert bot.user_sessions[1]["stage"] == "restart_confirmation"
    bot.process_user_message(1, "нет")
    assert bot.user_sessions[1] == before
    bot.process_user_message(1, "/restart")
    bot.process_user_message(1, "да")
    assert bot.user_sessions[1]["current_question"] == 0
    assert bot.user_sessions[1]["answers"] == []


def test_cancel_clears_only_current_user():
    begin(1)
    begin(2)
    second = deepcopy(bot.user_sessions[2])
    bot.process_user_message(1, "/cancel")
    assert 1 not in bot.user_sessions
    assert bot.user_sessions[2] == second
    assert "Пришли" in bot.process_user_message(1, "/cancel")


def test_complete_test_and_late_answer():
    session = begin()
    for index, question in enumerate(session["test_data"]["questions"]):
        reply = bot.process_user_message(1, question["correct_option_id"])
        if index < len(session["test_data"]["questions"]) - 1:
            assert f"Вопрос {index + 2}/" in reply
    assert "100%" in reply and "проверка пройдена" in reply
    assert bot.user_sessions[1]["stage"] == "completed"
    before = deepcopy(bot.user_sessions[1])
    assert "уже завершён" in bot.process_user_message(1, "a")
    assert bot.user_sessions[1] == before
    assert bot.process_user_message(1, "/result") == reply
    bot.process_user_message(1, DESCRIPTION)
    assert bot.user_sessions[1]["stage"] == "awaiting_confirmation"


def test_completed_result_survives_invalid_new_description():
    session = begin()
    for question in session["test_data"]["questions"]:
        bot.process_user_message(1, question["correct_option_id"])
    before = deepcopy(bot.user_sessions[1])
    bot.process_user_message(1, "https://example.com/python")
    assert bot.user_sessions[1] == before


def test_internal_error_does_not_leak_or_consume_last_answer(monkeypatch):
    session = begin()
    for question in session["test_data"]["questions"][:-1]:
        bot.process_user_message(1, question["correct_option_id"])
    before = deepcopy(bot.user_sessions[1])
    with monkeypatch.context() as context:
        context.setattr(bot, "build_feedback", Mock(side_effect=RuntimeError("SECRET_TOKEN private/path")))
        reply = bot.process_user_message(1, "a")
    assert "SECRET" not in reply and "private" not in reply
    assert "Прогресс сохранён" in reply
    assert bot.user_sessions[1] == before
    assert "Тест завершён" in bot.process_user_message(1, "a")


@pytest.mark.parametrize("broken", [{}, {"stage": "in_progress"}, [], "bad"])
def test_corrupt_session_does_not_crash_and_can_be_cancelled(broken):
    bot.user_sessions[1] = broken
    assert "Не удалось" in bot.process_user_message(1, "a")
    bot.process_user_message(1, "/cancel")
    assert 1 not in bot.user_sessions


@pytest.mark.parametrize("update", [None, [], "bad", {}, {"update_type": "message_callback"},
                                    {"update_type": "message_created", "message": None}])
def test_malformed_or_unsupported_events_are_ignored(monkeypatch, update):
    send = sender_mock(monkeypatch)
    assert bot.handle_update(update)
    send.assert_not_called()
    assert not bot.user_sessions


@pytest.mark.parametrize("field, value", [("sender", None), ("sender", []), ("sender", {"user_id": 1, "is_bot": True}),
                                         ("sender", {"user_id": True, "is_bot": False}),
                                         ("recipient", None), ("recipient", {"chat_type": "chat"}),
                                         ("body", []), ("body", {"mid": []}), ("body", {"mid": ""})])
def test_invalid_envelope_does_not_route_to_a_user(monkeypatch, field, value):
    send = sender_mock(monkeypatch)
    update = event()
    update["message"][field] = value
    assert bot.handle_update(update)
    send.assert_not_called()


@pytest.mark.parametrize("text", [None, "", {}, []])
def test_attachments_without_usable_caption_get_help(monkeypatch, text):
    send = sender_mock(monkeypatch)
    begin()
    before = deepcopy(bot.user_sessions[1])
    update = event(text=text)
    update["message"]["body"]["attachments"] = [{"type": "image"}]
    assert bot.handle_update(update)
    assert send.call_count == 1
    # Повторный показ вопроса добавляет только время отправки, но не ответы.
    assert bot.user_sessions[1]["answers"] == before["answers"]
    assert bot.user_sessions[1]["current_question"] == before["current_question"]


def test_forward_without_body_gets_text_prompt(monkeypatch):
    send = sender_mock(monkeypatch)
    update = event()
    update["message"]["body"] = None
    assert bot.handle_update(update)
    assert "текст" in send.call_args.args[1]
    assert not bot.user_sessions
    assert bot.handle_update(update)
    assert send.call_count == 1


def test_duplicate_message_id_is_counted_once(monkeypatch):
    send = sender_mock(monkeypatch)
    begin()
    update = event(text="a")
    assert bot.handle_update(update)
    assert bot.handle_update(update)
    assert len(bot.user_sessions[1]["answers"]) == 1
    assert send.call_count == 1


def test_same_message_id_is_scoped_to_sender(monkeypatch):
    sender_mock(monkeypatch)
    begin(1)
    begin(2)
    bot.handle_update(event(text="a", user_id=1))
    bot.handle_update(event(text="b", user_id=2))
    assert bot.user_sessions[1]["answers"][0]["selected_option_id"] == "a"
    assert bot.user_sessions[2]["answers"][0]["selected_option_id"] == "b"


def test_delivery_retry_does_not_apply_answer_twice(monkeypatch):
    send = sender_mock(monkeypatch)
    send.side_effect = [requests.Timeout(), Mock(json=lambda: {})]
    begin()
    update = event(text="a")
    assert not bot.handle_update(update)
    assert len(bot.user_sessions[1]["answers"]) == 1
    assert bot.handle_update(update)
    assert len(bot.user_sessions[1]["answers"]) == 1
    assert send.call_args_list[0] == send.call_args_list[1]


def test_pending_delivery_blocks_next_message_only_for_that_user(monkeypatch):
    send = sender_mock(monkeypatch)
    send.side_effect = requests.Timeout()
    begin()
    assert not bot.handle_update(event(text="a"))
    before = deepcopy(bot.user_sessions[1])
    assert not bot.handle_update(event(mid="m2", text="b"))
    assert bot.user_sessions[1] == before
    send.side_effect = None
    assert bot.handle_update(event(user_id=2))
    assert 2 in bot.user_sessions


def test_queued_answer_sent_before_new_question_is_rejected(monkeypatch):
    send = sender_mock(monkeypatch)
    begin()
    bot.handle_update(event(mid="m1", text="a", timestamp=1000))
    assert bot.user_sessions[1]["question_shown_at"] == 2000
    bot.handle_update(event(mid="m2", text="b", timestamp=1500))
    assert len(bot.user_sessions[1]["answers"]) == 1
    assert "не засчитано" in send.call_args.args[1]
    bot.handle_update(event(mid="m3", text="b", timestamp=2500))
    assert len(bot.user_sessions[1]["answers"]) == 2


def test_duplicate_after_cancel_does_not_recreate_test(monkeypatch):
    sender_mock(monkeypatch)
    update = event()
    bot.handle_update(update)
    bot.process_user_message(1, "/cancel")
    bot.handle_update(update)
    assert 1 not in bot.user_sessions


def test_cache_is_bounded(monkeypatch):
    sender_mock(monkeypatch)
    monkeypatch.setattr(bot, "MAX_CACHED_MESSAGES", 3)
    for index in range(10):
        bot.handle_update(event(mid=f"m{index}", text="/help"))
    assert len(bot._processed_messages) == 3


def test_long_feedback_is_split_and_resumes_at_failed_part(monkeypatch):
    send = sender_mock(monkeypatch)
    monkeypatch.setattr(bot, "process_user_message", Mock(return_value="x" * 8500))
    send.side_effect = [Mock(), requests.Timeout(), Mock(), Mock()]
    update = event()
    assert not bot.handle_update(update)
    assert bot.handle_update(update)
    assert [len(call.args[1]) for call in send.call_args_list] == [4000, 4000, 4000, 500]
    assert bot.process_user_message.call_count == 1


@pytest.mark.parametrize("payload", [None, [], {}, {"updates": None}, {"updates": {}},
                                     {"updates": [], "marker": "bad"}, {"updates": [], "marker": True}])
def test_bad_poll_response_is_rejected(monkeypatch, payload):
    monkeypatch.setattr(bot.requests, "get", Mock(return_value=Mock(json=lambda: payload)))
    with pytest.raises(ValueError):
        bot.get_updates(123)


def test_poll_keeps_marker_when_omitted(monkeypatch):
    monkeypatch.setattr(bot.requests, "get", Mock(return_value=Mock(json=lambda: {"updates": []})))
    assert bot.get_updates(123)["marker"] == 123


def test_poll_does_not_acknowledge_failed_delivery(monkeypatch):
    poll = Mock(side_effect=[{"updates": [event()], "marker": 123}, KeyboardInterrupt()])
    monkeypatch.setattr(bot, "BOT_TOKEN", "test-only")
    monkeypatch.setattr(bot, "get_updates", poll)
    handler = Mock(side_effect=[False, True])
    monkeypatch.setattr(bot, "handle_update", handler)
    monkeypatch.setattr(bot.time, "sleep", Mock())
    with pytest.raises(KeyboardInterrupt):
        bot.main()
    assert poll.call_args_list[0].args == (None,)
    assert poll.call_args_list[1].args == (123,)
    assert handler.call_count == 2
    assert handler.call_args_list[0] == handler.call_args_list[1]


def test_one_event_failure_does_not_prevent_other_users(monkeypatch):
    monkeypatch.setattr(bot, "BOT_TOKEN", "test-only")
    monkeypatch.setattr(bot, "get_updates", Mock(side_effect=[
        {"updates": [event(user_id=1), event(user_id=2)], "marker": 123}, KeyboardInterrupt(),
    ]))
    handler = Mock(side_effect=[RuntimeError("bad update"), True, True])
    monkeypatch.setattr(bot, "handle_update", handler)
    monkeypatch.setattr(bot.time, "sleep", Mock())
    with pytest.raises(KeyboardInterrupt):
        bot.main()
    assert handler.call_count == 3
    assert [call.args[0]["message"]["sender"]["user_id"] for call in handler.call_args_list] == [1, 2, 1]


@pytest.mark.parametrize("status", [403, 404])
def test_unavailable_dialog_does_not_block_delivery(monkeypatch, status):
    send = sender_mock(monkeypatch)
    response = requests.Response()
    response.status_code = status
    send.side_effect = requests.HTTPError(response=response)
    assert bot.handle_update(event())
    assert bot.handle_update(event())
    assert send.call_count == 1


@pytest.mark.parametrize("status", [401, 429, 500, 503])
def test_transient_or_configuration_failure_keeps_reply_for_retry(monkeypatch, status):
    send = sender_mock(monkeypatch)
    response = requests.Response()
    response.status_code = status
    send.side_effect = requests.HTTPError(response=response)
    begin()
    assert not bot.handle_update(event(text="a"))
    send.side_effect = None
    assert bot.handle_update(event(text="a"))
    assert len(bot.user_sessions[1]["answers"]) == 1


def test_outgoing_validation_and_rate_limit(monkeypatch):
    post = Mock(return_value=Mock())
    monkeypatch.setattr(bot.requests, "post", post)
    monkeypatch.setattr(bot.time, "monotonic", lambda: 100)
    sleep = Mock()
    monkeypatch.setattr(bot.time, "sleep", sleep)
    bot.send_message(1, "Первый ответ")
    bot.send_message(1, "Второй ответ")
    sleep.assert_called_once_with(0.55)
    assert post.call_count == 2
    for user_id, text in [(True, "text"), (1, None), (1, ""), (1, "x" * 4001)]:
        with pytest.raises(ValueError):
            bot.send_message(user_id, text)

# SPDX-FileCopyrightText: 2025 Marlon W (Mawoka)
#
# SPDX-License-Identifier: MPL-2.0
"""A player's language can change while a question is live.

`game:{pin}:players:languages` holds what players last picked and is what emits read; a submitted
answer carries the language it was given in and is scored in that language.
"""

import json
import random
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from classquiz import socket_server
from classquiz.db.models import (
    GamePlayer,
    PlayGame,
    QuestionTranslation,
    QuizQuestion,
    QuizQuestionType,
    QuizTranslation,
    VotingQuizAnswer,
)
from classquiz.routers import live
from classquiz.tests.test_translations import play_game

PIN = "123456"
ADMIN_SID = "admin-sid"
ALICE_SID = "alice-sid"
LANGUAGES_KEY = f"game:{PIN}:players:languages"


@pytest.fixture
def mocks(monkeypatch):
    redis = AsyncMock()
    sio = AsyncMock()
    game = play_game(translations={"es": QuizTranslation(title="Hola")})
    game.current_question = 0
    monkeypatch.setattr(socket_server, "redis", redis)
    monkeypatch.setattr(socket_server, "sio", sio)
    monkeypatch.setattr(PlayGame, "get_from_redis", AsyncMock(return_value=game))
    monkeypatch.setattr(PlayGame, "save", AsyncMock())
    return redis, sio, game


def hash_only_for(key: str, content: dict):
    async def hgetall(requested):
        return content if requested == key else {}

    return hgetall


def admin_session(monkeypatch):
    monkeypatch.setattr(
        socket_server, "get_session", AsyncMock(return_value={"admin": True, "game_pin": PIN, "username": None})
    )


async def alice_submits(redis, monkeypatch, **answer):
    async def get(key):
        return datetime.now().isoformat() if key.endswith(":current_time") else None

    redis.get.side_effect = get
    redis.scard.return_value = 5
    monkeypatch.setattr(
        socket_server,
        "get_session",
        AsyncMock(return_value={"admin": False, "game_pin": PIN, "username": "alice", "ping": 0}),
    )
    monkeypatch.setattr(socket_server, "has_already_answered", AsyncMock(return_value=False))

    await socket_server.submit_answer(ALICE_SID, {"question_index": 0, **answer})

    _key, _username, score = redis.hincrby.await_args.args
    return score


@pytest.mark.asyncio
async def test_answer_scores_in_the_language_it_was_submitted_in(mocks, monkeypatch):
    redis, _sio, _game = mocks

    assert await alice_submits(redis, monkeypatch, answer="cuatro", language="es") > 0


@pytest.mark.asyncio
async def test_answer_is_stored_in_the_authored_wording(mocks, monkeypatch):
    redis, _sio, _game = mocks

    await alice_submits(redis, monkeypatch, answer="cuatro", language="es")

    _key, stored = redis.set.await_args.args
    assert json.loads(stored)[0]["answer"] == "four"


@pytest.mark.asyncio
async def test_answer_in_an_unknown_language_is_scored_against_the_authored_wording(mocks, monkeypatch):
    redis, _sio, _game = mocks

    assert await alice_submits(redis, monkeypatch, answer="four", language="xx") > 0


@pytest.mark.asyncio
async def test_solutions_follow_the_players_language(mocks, monkeypatch):
    redis, sio, game = mocks
    admin_session(monkeypatch)
    redis.hgetall.side_effect = hash_only_for(LANGUAGES_KEY, {"alice": "es"})
    redis.smembers.return_value = {GamePlayer(username="alice", sid=ALICE_SID).model_dump_json()}

    await socket_server.show_solutions(ADMIN_SID, {})

    spanish = game.questions[0].localized("es").model_dump(exclude={"translations"})
    sio.emit.assert_any_await("solutions", spanish, room=ALICE_SID)


@pytest.mark.asyncio
async def test_api_question_start_emits_in_the_players_language(mocks, monkeypatch):
    redis, sio, game = mocks
    redis.get.return_value = game.model_dump_json()
    redis.smembers.return_value = {GamePlayer(username="alice", sid=ALICE_SID).model_dump_json()}
    redis.hgetall.side_effect = hash_only_for(LANGUAGES_KEY, {"alice": "es"})
    monkeypatch.setattr(live, "redis", redis)
    monkeypatch.setattr(live, "sio", sio)
    monkeypatch.setattr(live, "check_api_key", AsyncMock(return_value=game.user_id))

    await live.set_next_question(PIN, 0, "api-key")

    (_event, payload), _kwargs = next(c for c in sio.emit.await_args_list if c.kwargs["room"] == ALICE_SID)
    assert payload["question"]["question"] == "¿Cuánto es 2+2?"
    assert payload["language"] == "es"


@pytest.mark.asyncio
async def test_rejoin_greets_the_player_in_their_chosen_language(mocks, monkeypatch):
    redis, sio, game = mocks

    async def get(key):
        return {f"game:{PIN}": game.model_dump_json(), f"game_session:{PIN}:players:alice": "old-sid"}.get(key)

    async def hget(key, field):
        return "es" if (key, field) == (LANGUAGES_KEY, "alice") else None

    redis.get.side_effect = get
    redis.hget.side_effect = hget
    monkeypatch.setattr(socket_server, "save_session", AsyncMock())

    await socket_server.rejoin_game(ALICE_SID, {"game_pin": PIN, "username": "alice", "old_sid": "old-sid"})

    sio.emit.assert_any_await("rejoined_game", game.to_player_data("es"), room=ALICE_SID)


def player_session(monkeypatch, **overrides):
    session = {"admin": False, "game_pin": PIN, "username": "alice", **overrides}
    monkeypatch.setattr(socket_server, "get_session", AsyncMock(return_value=session))


@pytest.mark.asyncio
async def test_switch_updates_the_players_language(mocks, monkeypatch):
    redis, _sio, game = mocks
    player_session(monkeypatch)
    redis.get.return_value = ALICE_SID

    result = await socket_server.set_language(ALICE_SID, {"language": "es"})

    redis.hset.assert_awaited_once_with(LANGUAGES_KEY, "alice", "es")
    assert result == game.to_player_data("es") != game.to_player_data(None)


@pytest.mark.asyncio
async def test_switch_to_a_language_the_quiz_does_not_offer_falls_back_to_the_original(mocks, monkeypatch):
    redis, _sio, game = mocks
    player_session(monkeypatch)
    redis.get.return_value = ALICE_SID

    result = await socket_server.set_language(ALICE_SID, {"language": "de"})

    redis.hdel.assert_awaited_once_with(LANGUAGES_KEY, "alice")
    redis.hset.assert_not_awaited()
    assert result == game.to_player_data(None) != game.to_player_data("es")


@pytest.mark.asyncio
async def test_switch_from_a_socket_that_no_longer_owns_the_name_is_ignored(mocks, monkeypatch):
    redis, _sio, _game = mocks
    player_session(monkeypatch)
    redis.get.return_value = None

    assert await socket_server.set_language(ALICE_SID, {"language": "es"}) is None

    redis.hset.assert_not_awaited()
    redis.hdel.assert_not_awaited()


@pytest.mark.asyncio
async def test_switch_from_an_admin_session_is_ignored(mocks, monkeypatch):
    redis, _sio, _game = mocks
    player_session(monkeypatch, admin=True)
    redis.get.return_value = ALICE_SID

    assert await socket_server.set_language(ALICE_SID, {"language": "es"}) is None

    redis.hset.assert_not_awaited()
    redis.hdel.assert_not_awaited()


@pytest.mark.asyncio
async def test_switch_from_a_socket_that_never_joined_is_ignored(mocks, monkeypatch):
    redis, _sio, _game = mocks
    monkeypatch.setattr(socket_server, "get_session", AsyncMock(return_value={"session_id": "abc"}))

    assert await socket_server.set_language(ALICE_SID, {"language": "es"}) is None

    redis.hset.assert_not_awaited()
    redis.hdel.assert_not_awaited()


@pytest.mark.asyncio
async def test_joining_without_a_language_clears_a_stale_preference(mocks, monkeypatch):
    redis, _sio, game = mocks

    async def get(key):
        return game.model_dump_json() if key == f"game:{PIN}" else None

    redis.get.side_effect = get
    monkeypatch.setattr(socket_server, "save_session", AsyncMock())
    monkeypatch.setattr(GamePlayer, "to_player_stack", AsyncMock())

    await socket_server.join_game(ALICE_SID, {"game_pin": PIN, "username": "alice"})

    redis.hdel.assert_awaited_once_with(LANGUAGES_KEY, "alice")
    redis.hset.assert_not_awaited()


def order_question() -> QuizQuestion:
    return QuizQuestion(
        question="Sort them",
        time="20",
        type=QuizQuestionType.ORDER,
        answers=[VotingQuizAnswer(answer=f"a{i}") for i in range(6)],
        translations={"es": QuestionTranslation(question="Ordénalos", answers=[f"b{i}" for i in range(6)])},
    )


def authored_order(question, language):
    payload = socket_server.player_question(PIN, 0, question, language)
    return [int(a["answer"][1:]) for a in payload["question"]["answers"]]


def test_order_shuffle_is_the_same_in_every_language():
    question = order_question()
    assert authored_order(question, "es") == authored_order(question, None) == authored_order(question, "es")
    assert authored_order(question, None) != list(range(6))
    assert socket_server.player_question(PIN, 0, question, "es")["language"] == "es"


def test_order_shuffle_cannot_be_recomputed_from_public_values(monkeypatch):
    # The authored order is the solution, so a player who knows the pin and the question number must
    # not be able to rebuild the permutation and invert it.
    question = order_question()
    public_seed = list(range(6))
    random.Random(f"{PIN}:0").shuffle(public_seed)

    # Fixed secrets, checked not to collide with the public permutation or each other, so the
    # outcome does not depend on the environment's secret_key.
    monkeypatch.setattr(socket_server.settings, "secret_key", "secret-a")
    shown = authored_order(question, None)
    assert shown != public_seed

    monkeypatch.setattr(socket_server.settings, "secret_key", "secret-b")
    assert authored_order(question, None) not in (shown, public_seed)

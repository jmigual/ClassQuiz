# SPDX-FileCopyrightText: 2025 Marlon W (Mawoka)
#
# SPDX-License-Identifier: MPL-2.0
"""A player's language switch applies from the next question, never to the one on screen.

`game:{pin}:players:languages` holds what players last picked; `...:question_languages` is a copy
taken when each question goes out, and is what emits and scoring read.
"""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from classquiz import socket_server
from classquiz.db.models import GamePlayer, PlayGame, QuizTranslation
from classquiz.routers import live
from classquiz.tests.test_translations import play_game

PIN = "123456"
ADMIN_SID = "admin-sid"
ALICE_SID = "alice-sid"
LANGUAGES_KEY = f"game:{PIN}:players:languages"
COPY_KEY = f"game:{PIN}:players:question_languages"


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


@pytest.mark.asyncio
async def test_answer_scores_against_the_language_the_question_went_out_in(mocks, monkeypatch):
    redis, _sio, _game = mocks

    async def hget(key, field):
        return "es" if (key, field) == (COPY_KEY, "alice") else None

    async def get(key):
        return datetime.now().isoformat() if key.endswith(":current_time") else None

    redis.hget.side_effect = hget
    redis.get.side_effect = get
    redis.scard.return_value = 5
    monkeypatch.setattr(
        socket_server,
        "get_session",
        AsyncMock(return_value={"admin": False, "game_pin": PIN, "username": "alice", "ping": 0}),
    )
    monkeypatch.setattr(socket_server, "has_already_answered", AsyncMock(return_value=False))

    await socket_server.submit_answer(ALICE_SID, {"question_index": 0, "answer": "cuatro"})

    _key, _username, score = redis.hincrby.await_args.args
    assert score > 0


@pytest.mark.asyncio
async def test_solutions_follow_the_language_the_question_went_out_in(mocks, monkeypatch):
    redis, sio, game = mocks
    admin_session(monkeypatch)
    redis.hgetall.side_effect = hash_only_for(COPY_KEY, {"alice": "es"})
    redis.smembers.return_value = {GamePlayer(username="alice", sid=ALICE_SID).model_dump_json()}

    await socket_server.show_solutions(ADMIN_SID, {})

    spanish = game.questions[0].localized("es").model_dump(exclude={"translations"})
    sio.emit.assert_any_await("solutions", spanish, room=ALICE_SID)


@pytest.mark.asyncio
async def test_api_question_start_copies_player_languages_and_emits_in_them(mocks, monkeypatch):
    redis, sio, game = mocks
    redis.get.return_value = game.model_dump_json()
    redis.smembers.return_value = {GamePlayer(username="alice", sid=ALICE_SID).model_dump_json()}
    # The emit reads what the snapshot wrote, so the hashes have to behave like hashes.
    hashes = {LANGUAGES_KEY: {"alice": "es"}}

    async def hset(key, mapping):
        hashes[key] = mapping

    async def hgetall(key):
        return hashes.get(key, {})

    redis.hgetall.side_effect = hgetall
    redis.hset.side_effect = hset
    monkeypatch.setattr(live, "redis", redis)
    monkeypatch.setattr(live, "sio", sio)
    monkeypatch.setattr(live, "check_api_key", AsyncMock(return_value=game.user_id))

    await live.set_next_question(PIN, 0, "api-key")

    redis.hset.assert_awaited_once_with(COPY_KEY, mapping={"alice": "es"})
    (_event, payload), _kwargs = next(c for c in sio.emit.await_args_list if c.kwargs["room"] == ALICE_SID)
    assert payload["question"]["question"] == "¿Cuánto es 2+2?"


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


@pytest.mark.asyncio
async def test_question_start_copies_player_languages(mocks, monkeypatch):
    redis, _sio, _game = mocks
    admin_session(monkeypatch)
    redis.smembers.return_value = set()
    redis.hgetall.side_effect = hash_only_for(LANGUAGES_KEY, {"alice": "es"})

    await socket_server.set_question_number(ADMIN_SID, "0")

    redis.delete.assert_awaited_once_with(COPY_KEY)
    redis.hset.assert_awaited_once_with(COPY_KEY, mapping={"alice": "es"})

    redis.delete.reset_mock()
    redis.hset.reset_mock()
    redis.hgetall.side_effect = hash_only_for(LANGUAGES_KEY, {})

    await socket_server.set_question_number(ADMIN_SID, "0")

    redis.delete.assert_awaited_once_with(COPY_KEY)
    redis.hset.assert_not_awaited()


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

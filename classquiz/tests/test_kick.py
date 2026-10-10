# SPDX-FileCopyrightText: 2025 Marlon W (Mawoka)
#
# SPDX-License-Identifier: MPL-2.0
"""Kicking a player must free their name and cut their socket, and must be harmless to repeat."""

from unittest.mock import AsyncMock

import pytest

from classquiz import socket_server

PIN = "123456"
ADMIN_SID = "admin-sid"
PLAYER_SID = "player-sid"


@pytest.fixture
def mocks(monkeypatch):
    redis = AsyncMock()
    redis.get.return_value = PLAYER_SID
    sio = AsyncMock()
    monkeypatch.setattr(socket_server, "redis", redis)
    monkeypatch.setattr(socket_server, "sio", sio)
    monkeypatch.setattr(
        socket_server,
        "get_session",
        AsyncMock(return_value={"admin": True, "game_pin": PIN}),
    )
    return redis, sio


@pytest.mark.asyncio
async def test_kick_frees_the_name_and_ends_the_players_socket(mocks):
    redis, sio = mocks
    await socket_server.kick_player(ADMIN_SID, {"username": "alice"})

    redis.delete.assert_awaited_once_with(f"game_session:{PIN}:players:alice")
    redis.hdel.assert_any_await(f"game:{PIN}:players:languages", "alice")
    redis.hdel.assert_any_await(f"game:{PIN}:players:custom_fields", "alice")
    sio.emit.assert_awaited_once_with("kick", room=PLAYER_SID)
    sio.disconnect.assert_awaited_once_with(PLAYER_SID)


@pytest.mark.asyncio
async def test_kicking_an_unknown_player_emits_nothing(mocks):
    redis, sio = mocks
    redis.get.return_value = None
    await socket_server.kick_player(ADMIN_SID, {"username": "alice"})

    sio.emit.assert_not_awaited()
    sio.disconnect.assert_not_awaited()
    redis.delete.assert_not_awaited()

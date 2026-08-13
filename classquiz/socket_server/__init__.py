# SPDX-FileCopyrightText: 2023 Marlon W (Mawoka)
#
# SPDX-License-Identifier: MPL-2.0


import base64
import hashlib
import json
import os
import random
from typing import Callable

import socketio
from cryptography.fernet import Fernet

from classquiz.config import redis, settings
from classquiz.db.models import (
    PlayGame,
    QuizQuestionType,
    GameSession,
    GamePlayer,
    VotingQuizAnswer,
    AnswerDataList,
    AnswerData,
)
from pydantic import BaseModel, ValidationError
from datetime import datetime

from classquiz.socket_server.helpers import (
    check_answer,
    check_captcha,
    has_already_answered,
)
from .models import (
    RejoinGameData,
    JoinGameData,
    ReturnQuestion,
    SubmitAnswerData,
    RegisterAsAdminData,
    KickPlayerInput,
    ConnectSessionIdEvent,
)

from classquiz.socket_server.export_helpers import save_quiz_to_storage
from classquiz.socket_server.session import get_session, save_session

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=[])
settings = settings()


def get_fernet_key() -> bytes:
    hlib = hashlib.sha256()
    hlib.update(settings.secret_key.encode("utf-8"))
    return base64.urlsafe_b64encode(hlib.hexdigest().encode("latin-1")[:32])


fernet = Fernet(get_fernet_key())


async def generate_final_results(game_data: PlayGame, game_pin: str) -> dict:
    results = {}
    for i in range(len(game_data.questions)):
        redis_res = await redis.get(f"game_session:{game_pin}:{i}")
        if redis_res is None:
            continue
        else:
            results[str(i)] = json.loads(redis_res)
    return results


def calculate_score(z: float, t: int) -> int:
    t = t * 1000
    res = (t - z) / t
    return int(res * 1000)


async def set_answer(answers, game_pin: str, q_index: int, data: AnswerData) -> AnswerDataList:
    if answers is None:
        answers = AnswerDataList([data])
    else:
        answers = AnswerDataList.model_validate_json(answers)
        answers.append(data)
    await redis.set(
        f"game_session:{game_pin}:{q_index}",
        answers.model_dump_json(),
        ex=7200,
    )
    return answers


async def emit_per_player_language(game_pin: str, event: str, payload_for: Callable[[str | None], dict]) -> set[str]:
    """Emit `event` to every player in the language they joined with, returning the languages present.

    Question text is per-player now, so it can't go out as one broadcast to the game_pin room.
    `payload_for` is expected to memoize, so a room of 200 speaking three languages builds three
    payloads rather than two hundred. Callers must emit to `admin:{game_pin}` themselves — the host
    used to be covered by the game_pin broadcast and no longer is.
    """
    languages_key = f"game:{game_pin}:players:languages"
    player_languages = await redis.hgetall(languages_key)
    # Refreshed on every question, or a game running longer than the TTL would silently drop every
    # player back to the authored language mid-session.
    await redis.expire(languages_key, 7200)
    active_languages = set()
    for raw_player in await redis.smembers(f"game_session:{game_pin}:players"):
        player = GamePlayer.model_validate_json(raw_player)
        # A box controller joins the player set with no sid; there is no socket to emit to.
        if player.sid is None:
            continue
        language = player_languages.get(player.username)
        if language is not None:
            active_languages.add(language)
        await sio.emit(event, payload_for(language), room=player.sid)
    return active_languages


@sio.event
async def rejoin_game(sid: str, data: dict):
    redis_res = await redis.get(f"game:{data['game_pin']}")
    if redis_res is None:
        await sio.emit("game_not_found", room=sid)
        return
    try:
        data = RejoinGameData(**data)
    except ValidationError as e:
        await sio.emit("error", room=sid)
        print(e)
    redis_sid_key = f"game_session:{data.game_pin}:players:{data.username}"
    old_sid = await redis.get(redis_sid_key)
    if old_sid != data.old_sid:
        return
    encrypted_datetime = fernet.encrypt(datetime.now().isoformat().encode("utf-8")).decode("utf-8")
    await sio.emit("time_sync", encrypted_datetime, room=sid)
    await redis.set(redis_sid_key, sid)
    await redis.srem(
        f"game_session:{data.game_pin}:players",
        GamePlayer(username=data.username, sid=data.old_sid).model_dump_json(),
    )
    await redis.sadd(
        f"game_session:{data.game_pin}:players",
        GamePlayer(username=data.username, sid=sid).model_dump_json(),
    )
    game_data = PlayGame.model_validate_json(redis_res)
    session = {
        "game_pin": data.game_pin,
        "username": data.username,
        "sid_custom": sid,
        "admin": False,
        # Server-authoritative, so a reconnecting client can't switch language mid-game.
        "language": await redis.hget(f"game:{data.game_pin}:players:languages", data.username),
    }
    await save_session(sid, sio, session)
    await sio.enter_room(sid, data.game_pin)
    await sio.emit(
        "rejoined_game",
        game_data.to_player_data(),
        room=sid,
    )


@sio.event
async def join_game(sid: str, data: dict):
    redis_res = await redis.get(f"game:{data['game_pin']}")
    if redis_res is None:
        await sio.emit("game_not_found", room=sid)
        return
    try:
        data = JoinGameData(**data)
    except ValidationError as e:
        await sio.emit("error", room=sid)
        print(e)
        return
    game_data = PlayGame.model_validate_json(redis_res)
    if game_data.started:
        await sio.emit("game_already_started", room=sid)
        return
    # +++ START checking captcha +++
    if game_data.captcha_enabled:
        captcha_res = check_captcha(data.captcha)
        if not captcha_res:
            return
    # --- END checking captcha ---
    if await redis.get(f"game_session:{data.game_pin}:players:{data.username}") is not None:
        await sio.emit("username_already_exists", room=sid)
        return

    session = {
        "game_pin": data.game_pin,
        "username": data.username,
        "sid_custom": sid,
        "admin": False,
        "language": data.language,
    }
    await save_session(sid, sio, session)
    await sio.emit(
        "joined_game",
        game_data.to_player_data(),
        room=sid,
    )
    await redis.set(f"game_session:{data.game_pin}:players:{data.username}", sid, ex=7200)
    await GamePlayer(username=data.username, sid=sid).to_player_stack(data.game_pin)

    if data.custom_field == "":
        data.custom_field = None
    if data.custom_field is not None:
        await redis.hset(
            f"game:{data.game_pin}:players:custom_fields",
            data.username,
            data.custom_field,
        )

    if data.language is not None:
        languages_key = f"game:{data.game_pin}:players:languages"
        await redis.hset(languages_key, data.username, data.language)
        await redis.expire(languages_key, 7200)

    await sio.emit(
        "player_joined",
        {"username": data.username, "sid": sid},
        room=f"admin:{data.game_pin}",
    )
    # +++ Time-Sync +++
    encrypted_datetime = fernet.encrypt(datetime.now().isoformat().encode("utf-8")).decode("utf-8")
    await sio.emit("time_sync", encrypted_datetime, room=sid)
    # --- Time-Sync ---
    await sio.enter_room(sid, data.game_pin)


@sio.event
async def start_game(sid: str, _data: dict):
    session = await get_session(sid, sio)
    if not session["admin"]:
        return
    game_data = await PlayGame.get_from_redis(session["game_pin"])
    game_data.started = True
    await game_data.save(session["game_pin"])
    await redis.delete(f"game_in_lobby:{game_data.user_id.hex}")
    await sio.emit("start_game", room=session["game_pin"])


@sio.event
async def register_as_admin(sid: str, data: dict):
    try:
        data = RegisterAsAdminData(**data)
    except ValidationError as e:
        await sio.emit("error", room=sid)
        print(e)
        return
    game_pin = data.game_pin
    game_id = data.game_id
    if await redis.get(f"game_session:{game_pin}") is not None:
        await sio.emit("already_registered_as_admin", room=sid)
        return
    await GameSession(admin=sid, game_id=game_id, answers=[]).save(game_pin)
    await sio.emit(
        "registered_as_admin",
        {"game_id": game_id, "game": await redis.get(f"game:{game_pin}")},
        room=sid,
    )
    session = {"game_pin": game_pin, "admin": True, "remote": False}
    await save_session(sid, sio, session)
    await sio.enter_room(sid, game_pin)
    await sio.enter_room(sid, f"admin:{data.game_pin}")


@sio.event
async def get_question_results(sid: str, data: dict):
    session = await get_session(sid, sio)
    if not session["admin"]:
        return
    game_pin = session["game_pin"]
    answer_data_list = await AnswerDataList.get_redis_or_empty(game_pin, data["question_number"])
    game_data = await PlayGame.get_from_redis(game_pin)
    game_data.question_show = False
    await game_data.save(game_pin)
    await sio.emit("question_results", answer_data_list.model_dump(), room=game_pin)


@sio.event
async def set_question_number(sid: str, data: str):
    # data is just a number (as a str) of the question
    session = await get_session(sid, sio)
    if not session["admin"]:
        return
    game_pin = session["game_pin"]
    game_data = await PlayGame.get_from_redis(session["game_pin"])
    game_data.current_question = int(float(data))
    game_data.question_show = True
    await game_data.save(session["game_pin"])
    await redis.set(f"game:{session['game_pin']}:current_time", datetime.now().isoformat(), ex=7200)
    question_index = int(float(data))
    base_question = game_data.questions[question_index]
    if base_question.type == QuizQuestionType.SLIDE:
        await sio.emit(
            "set_question_number",
            {
                "question_index": question_index,
            },
            room=sid,
        )
        return

    payloads: dict[str | None, dict] = {}

    def payload_for(language: str | None) -> dict:
        # Cache by language, not by player: 200 people speaking three languages build three
        # payloads, not two hundred.
        if language not in payloads:
            question = base_question.localized(language)
            temp_return = question.model_dump(exclude={"translations"})
            if question.type == QuizQuestionType.VOTING:
                for i in range(len(temp_return["answers"])):
                    temp_return["answers"][i] = VotingQuizAnswer(**temp_return["answers"][i])
            temp_return["type"] = question.type
            if temp_return["type"] == QuizQuestionType.ORDER:
                random.shuffle(temp_return["answers"])
            payloads[language] = {
                "question_index": question_index,
                # Never ship the other languages to a player's device.
                "question": ReturnQuestion(**temp_return).model_dump(exclude={"translations"}),
            }
        return payloads[language]

    active_languages = await emit_per_player_language(game_pin, "set_question_number", payload_for)

    # The host needs its own emit plus the languages to stack the question in. Those come from the
    # players just emitted to, not from the redis hash, so a kicked player (removed from the player
    # set, but never from the hash) stops appearing on the shared screen.
    await sio.emit(
        "set_question_number",
        {**payload_for(None), "languages": sorted(active_languages)},
        room=f"admin:{game_pin}",
    )


@sio.event
async def submit_answer(sid: str, data: dict):
    now = datetime.now()
    try:
        data = SubmitAnswerData(**data)
    except ValidationError as e:
        await sio.emit("error", room=sid)
        print(e)
        return
    data.answer = str(data.answer)
    session = await get_session(sid, sio)
    question_index = int(float(data.question_index))
    game_data = await PlayGame.get_from_redis(session["game_pin"])

    if question_index != game_data.current_question:
        await sio.emit("question_not_active", room=sid)
        return

    already_answered = await has_already_answered(session["game_pin"], question_index, session["username"])
    if already_answered:
        await sio.emit("already_replied", room=sid)
        return

    # Check against the wording this player was actually shown — every string comparison in
    # check_answer would otherwise miss on a translated answer — then store the authored
    # wording so results aggregate across languages.
    base_question = game_data.questions[question_index]
    answer_right, answer = check_answer(base_question.localized(session.get("language")), data)
    answer = base_question.authored_answer(session.get("language"), answer)
    latency = int(float(session["ping"]))
    time_q_started = datetime.fromisoformat(await redis.get(f"game:{session['game_pin']}:current_time"))
    diff = (time_q_started - now).total_seconds() * 1000  # - timedelta(milliseconds=latency)
    score = 0
    if answer_right:
        score = calculate_score(
            abs(diff) - latency,
            int(float(game_data.questions[question_index].time)),
        )
        if score > 1000:
            score = 1000
    await redis.hincrby(f"game_session:{session['game_pin']}:player_scores", session["username"], score)
    answer_data = AnswerData(
        username=session["username"],
        answer=answer,
        right=answer_right,
        time_taken=abs(diff) - latency,
        score=score,
    )
    answers = await redis.get(f"game_session:{session['game_pin']}:{data.question_index}")
    answers = await set_answer(
        answers,
        game_pin=session["game_pin"],
        data=answer_data,
        q_index=int(float(data.question_index)),
    )
    player_count = await redis.scard(f"game_session:{session['game_pin']}:players")
    await sio.emit("player_answer", {})
    if len(answers) == player_count:
        game_data = await PlayGame.get_from_redis(session["game_pin"])
        game_data.question_show = False
        await game_data.save(session["game_pin"])
        await sio.emit("everyone_answered", {})


@sio.event
async def get_final_results(sid: str, _data: dict):
    session: dict = await get_session(sid, sio)
    if not session["admin"]:
        return
    game_data = await PlayGame.get_from_redis(session["game_pin"])
    results = await generate_final_results(game_data, session["game_pin"])
    await sio.emit("final_results", results, room=session["game_pin"])


@sio.event
async def get_export_token(sid: str):
    session = await get_session(sid, sio)
    if not session["admin"]:
        return
    game_data = await PlayGame.get_from_redis(session["game_pin"])
    results = await generate_final_results(game_data, session["game_pin"])
    token = os.urandom(32).hex()
    await redis.set(f"export_token:{token}", json.dumps(results), ex=7200)
    await sio.emit("export_token", token, room=sid)


@sio.event
async def show_solutions(sid: str, _data: dict):
    session: dict = await get_session(sid, sio)
    game_data = await PlayGame.get_from_redis(session["game_pin"])
    if not session["admin"]:
        return
    game_pin = session["game_pin"]
    base_question = game_data.questions[game_data.current_question]
    payloads: dict[str | None, dict] = {}

    def payload_for(language: str | None) -> dict:
        if language not in payloads:
            # The solution has to be worded the same way the question was, and must not carry the
            # other languages along with it.
            payloads[language] = base_question.localized(language).model_dump(exclude={"translations"})
        return payloads[language]

    await emit_per_player_language(game_pin, "solutions", payload_for)
    await sio.emit("solutions", payload_for(None), room=f"admin:{game_pin}")


@sio.event
async def echo_time_sync(sid: str, data: str):
    then_dec = fernet.decrypt(data).decode("utf-8")
    then = datetime.fromisoformat(then_dec)
    now = datetime.now()
    delta = now - then
    session = await get_session(sid, sio)
    session["ping"] = delta.microseconds / 1000
    await save_session(sid, sio, session)


@sio.event
async def kick_player(sid: str, data: dict):
    try:
        data = KickPlayerInput(**data)
    except ValidationError as e:
        await sio.emit("error", room=sid)
        print(e)
        return

    session: dict = await get_session(sid, sio)
    if not session["admin"]:
        return

    player_sid = await redis.get(f"game_session:{session['game_pin']}:players:{data.username}")
    await redis.srem(
        f"game_session:{session['game_pin']}:players",
        GamePlayer(username=data.username, sid=player_sid).model_dump_json(),
    )
    await sio.leave_room(player_sid, session["game_pin"])
    await sio.emit("kick", room=player_sid)


class _RegisterAsRemoteInput(BaseModel):
    game_pin: str
    game_id: str


@sio.event
async def register_as_remote(sid: str, data: dict):
    try:
        data = _RegisterAsRemoteInput(**data)
    except ValidationError as e:
        await sio.emit("error", room=sid)
        print(e)
        return
    await sio.emit(
        "registered_as_admin",
        {"game_id": data.game_id, "game": await redis.get(f"game:{data.game_pin}")},
        room=sid,
    )
    await sio.emit("control_visibility", {"visible": False}, room=f"admin:{data.game_pin}")
    session = await get_session(sid, sio)
    session["game_pin"] = data.game_pin
    session["admin"] = True
    session["remote"] = True
    await save_session(sid, sio, session)
    await sio.enter_room(sid, data.game_pin)
    await sio.enter_room(sid, f"admin:{data.game_pin}")


class _SetControlVisibilityInput(BaseModel):
    visible: bool


@sio.event
async def set_control_visibility(sid: str, data: dict):
    try:
        data = _SetControlVisibilityInput(**data)
    except ValidationError as e:
        await sio.emit("error", room=sid)
        print(e)
        return
    session: dict = await get_session(sid, sio)
    await sio.emit(
        "control_visibility",
        {"visible": data.visible},
        room=f"admin:{session['game_pin']}",
    )


@sio.event
async def save_quiz(sid: str):
    session: dict = await get_session(sid, sio)
    if not session["admin"]:
        return
    await save_quiz_to_storage(session["game_pin"])
    await sio.emit("results_saved_successfully")


@sio.event
async def connect(sid: str, _environ, _auth):
    session_id = os.urandom(16).hex()
    print("Connection opened with handler")
    sio_session = {"session_id": session_id}
    await sio.save_session(sid, sio_session)
    await sio.emit("session_id", ConnectSessionIdEvent(session_id=session_id).dict())

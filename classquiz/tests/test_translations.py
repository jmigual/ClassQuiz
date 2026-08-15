# SPDX-FileCopyrightText: 2025 Marlon W (Mawoka)
#
# SPDX-License-Identifier: MPL-2.0
"""Per-player question language: the wording changes, the scoring must not.

Answers travel back to the server as strings, so showing a player a translated answer and then
checking it against the authored one silently marks every correct answer wrong. These cover that.
"""

import uuid

from classquiz.db.models import (
    ABCDQuizAnswer,
    PlayGame,
    QuestionTranslation,
    QuizQuestion,
    QuizQuestionType,
    TextQuizAnswer,
)
from classquiz.socket_server.helpers import check_answer
from classquiz.socket_server.models import SubmitAnswerData


def play_game(**overrides) -> PlayGame:
    defaults = dict(
        quiz_id=uuid.uuid4(),
        description="",
        user_id=uuid.uuid4(),
        title="quiz",
        questions=[abcd_question()],
        game_id=uuid.uuid4(),
        game_pin="123456",
    )
    defaults.update(overrides)
    return PlayGame(**defaults)


def abcd_question() -> QuizQuestion:
    return QuizQuestion(
        question="What is 2+2?",
        time="20",
        type=QuizQuestionType.ABCD,
        answers=[
            ABCDQuizAnswer(right=False, answer="three"),
            ABCDQuizAnswer(right=True, answer="four"),
        ],
        translations={"es": QuestionTranslation(question="¿Cuánto es 2+2?", answers=["tres", "cuatro"])},
    )


def test_localized_swaps_text_but_not_correctness():
    localized = abcd_question().localized("es")
    assert localized.question == "¿Cuánto es 2+2?"
    assert [a.answer for a in localized.answers] == ["tres", "cuatro"]
    assert [a.right for a in localized.answers] == [False, True]


def test_localized_is_identity_without_a_translation():
    question = abcd_question()
    assert question.localized(None) is question
    assert question.localized("de") is question


def test_localized_falls_back_field_by_field():
    question = abcd_question()
    question.translations["ca"] = QuestionTranslation(question="Quant és 2+2?", answers=[])
    localized = question.localized("ca")
    assert localized.question == "Quant és 2+2?"
    # No answer translations supplied, so the authored answers survive rather than blanking out.
    assert [a.answer for a in localized.answers] == ["three", "four"]


def test_localized_does_not_mutate_the_authored_question():
    question = abcd_question()
    question.localized("es")
    assert question.question == "What is 2+2?"
    assert [a.answer for a in question.answers] == ["three", "four"]


def test_a_translated_answer_still_scores_right():
    question = abcd_question()
    submission = SubmitAnswerData(question_index=0, answer="cuatro")
    assert check_answer(question.localized("es"), submission)[0]
    # The same submission against the authored wording is the bug these tests exist to catch.
    assert not check_answer(question, submission)[0]


def test_a_translated_wrong_answer_still_scores_wrong():
    question = abcd_question()
    submission = SubmitAnswerData(question_index=0, answer="tres")
    assert not check_answer(question.localized("es"), submission)[0]


def test_answers_are_stored_in_the_authored_wording():
    question = abcd_question()
    assert question.authored_answer("es", "cuatro") == "four"
    assert question.authored_answer("es", "tres") == "three"
    # Untranslated languages and free text pass straight through.
    assert question.authored_answer(None, "four") == "four"
    assert question.authored_answer("es", "typed something else") == "typed something else"


def test_text_question_checks_against_the_translated_expected_answer():
    question = QuizQuestion(
        question="Capital of Peru?",
        time="20",
        type=QuizQuestionType.TEXT,
        answers=[TextQuizAnswer(answer="Lima", case_sensitive=False)],
        translations={"ca": QuestionTranslation(question="Capital del Perú?", answers=["Lima ciutat"])},
    )
    submission = SubmitAnswerData(question_index=0, answer="lima ciutat")
    assert check_answer(question.localized("ca"), submission)[0]


def test_range_question_survives_a_language_with_no_answer_text():
    question = QuizQuestion(
        question="How tall is the tower?",
        time="20",
        type=QuizQuestionType.RANGE,
        answers={"min": 0, "max": 100, "min_correct": 40, "max_correct": 60},
        translations={"es": QuestionTranslation(question="¿Qué altura tiene?", answers=[])},
    )
    localized = question.localized("es")
    assert localized.question == "¿Qué altura tiene?"
    assert check_answer(localized, SubmitAnswerData(question_index=0, answer="50"))[0]


def test_available_languages_prefers_the_declared_list():
    game = play_game(languages=["Catalan", "French"])
    assert game.available_languages() == ["Catalan", "French"]


def test_available_languages_falls_back_to_translation_keys_when_undeclared():
    # Legacy quizzes saved before the declared list existed have no `languages`, so the
    # players' choices must still come from whatever the questions were translated into.
    game = play_game(languages=[])
    assert game.available_languages() == ["es"]


def test_available_languages_is_empty_with_neither():
    question = QuizQuestion(
        question="No translations here",
        time="20",
        type=QuizQuestionType.ABCD,
        answers=[ABCDQuizAnswer(right=True, answer="yes")],
    )
    game = play_game(languages=[], questions=[question])
    assert game.available_languages() == []

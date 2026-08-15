"""Where an implied `ask` gets inserted.

This is a small surface with an outsized failure mode: it breaks the *documented* form of
the command, and it breaks it at argparse level, so no amount of correct downstream code
helps. The bug these tests were written for shipped in the README — every flag was walked
past as though it were global, so `--provider mock --depth quick "…?"` put `ask` after
`--depth` and argparse rejected the lot.
"""

from __future__ import annotations

import argparse

import pytest

from app.cli import (
    COMMANDS,
    GLOBAL_FLAGS,
    _insert_default_command,
    build_parser,
    parse_args,
)

QUESTION = "Should I take the smaller offer with equity?"


def test_a_bare_question_gets_ask():
    assert _insert_default_command([QUESTION]) == ["ask", QUESTION]


def test_ask_is_inserted_after_global_flags_and_their_values():
    assert _insert_default_command(["--provider", "mock", QUESTION]) == [
        "--provider",
        "mock",
        "ask",
        QUESTION,
    ]


def test_ask_is_inserted_before_asks_own_flags():
    """The regression. `--depth` belongs to `ask`, not to the top-level parser."""
    assert _insert_default_command(["--provider", "mock", "--depth", "quick", QUESTION]) == [
        "--provider",
        "mock",
        "ask",
        "--depth",
        "quick",
        QUESTION,
    ]


def test_global_flags_are_hoisted_from_anywhere():
    """argparse needs them before the subcommand; nobody types in that order."""
    assert _insert_default_command(
        ["--provider", "mock", "--depth", "quick", "--quiet", QUESTION]
    ) == ["--provider", "mock", "--quiet", "ask", "--depth", "quick", QUESTION]


def test_a_global_flag_after_a_real_subcommand_is_hoisted_too():
    assert _insert_default_command(["cards", "--status", "due", "--json"]) == [
        "--json",
        "cards",
        "--status",
        "due",
    ]


def test_a_global_looking_value_is_not_hoisted_out_of_its_flag():
    """`--notes "--quiet"` means the note is the string `--quiet`, not a global flag.

    Only the hoisting is asserted here. argparse itself then refuses an option-looking
    value for `--notes`, which is stock behaviour and not this function's business — the
    `=` form below is how you actually pass one, and it survives hoisting too.
    """
    assert _insert_default_command(["--notes", "--quiet", QUESTION]) == [
        "ask",
        "--notes",
        "--quiet",
        QUESTION,
    ]
    args = parse_args(["--notes=--quiet", QUESTION])
    assert args.notes == "--quiet" and args.quiet is False


def test_the_documented_invocations_actually_parse():
    """These exact lines are in the README, which is where the bug was found."""
    args = parse_args(["--provider", "mock", QUESTION])
    assert args.command == "ask" and args.question == QUESTION and args.provider == "mock"

    args = parse_args(["--preset", "strategy", "--depth", "quick", QUESTION])
    assert args.command == "ask" and args.preset == "strategy" and args.depth == "quick"

    args = parse_args(["--provider", "mock", "--depth", "deep", "--notes", "n", QUESTION])
    assert args.command == "ask" and args.depth == "deep" and args.notes == "n"


def test_an_equals_form_global_flag_does_not_swallow_the_question():
    assert _insert_default_command(["--provider=mock", QUESTION]) == [
        "--provider=mock",
        "ask",
        QUESTION,
    ]


@pytest.mark.parametrize("command", COMMANDS)
def test_a_real_subcommand_is_never_displaced(command):
    assert _insert_default_command([command]) == [command]
    assert _insert_default_command(["--json", command]) == ["--json", command]


def test_a_question_that_looks_like_a_subcommand_is_still_a_subcommand():
    """`app.cli cards` cannot also mean "deliberate on the word cards".

    Ambiguity resolved in favour of the subcommand, because `ask cards` is one keystroke
    away and silently deliberating instead of listing would be the worse surprise.
    """
    assert _insert_default_command(["cards"]) == ["cards"]


def test_help_is_left_alone():
    with pytest.raises(SystemExit) as exit_info:
        parse_args(["--help"])
    assert exit_info.value.code == 0


def test_no_arguments_is_an_error_not_an_empty_question():
    with pytest.raises(SystemExit):
        parse_args([])


def test_every_global_flag_is_a_flag():
    assert all(name.startswith("-") for name in GLOBAL_FLAGS)


def test_global_flags_agree_with_the_parser():
    """Catches a global flag added to the parser but not to `GLOBAL_FLAGS`, and vice versa.

    The drift is invisible until somebody types the new flag: it would not be recognised as
    global, so it would become the insertion point and `ask` would land in front of it.
    """
    parser = build_parser()
    registered: dict[str, bool] = {}
    for action in parser._actions:  # noqa: SLF001 - the only way to enumerate registrations
        if not action.option_strings:
            continue  # positionals and the subparsers action
        for name in action.option_strings:
            registered[name] = action.nargs != 0

    assert set(registered) == set(GLOBAL_FLAGS), (
        f"GLOBAL_FLAGS disagrees with the parser: "
        f"only in parser {set(registered) - set(GLOBAL_FLAGS)}, "
        f"only in GLOBAL_FLAGS {set(GLOBAL_FLAGS) - set(registered)}"
    )
    for name, takes_value in registered.items():
        assert GLOBAL_FLAGS[name] == takes_value, (
            f"{name} disagrees on whether it takes a value"
        )


def test_every_subcommand_has_a_handler():
    """`COMMANDS` drives the default-command insertion; the parser drives dispatch.

    `divergence` was once missing from `COMMANDS`, so the CLI treated it as a question and
    spent three minutes against the rate limiter before saying anything.
    """
    parser = build_parser()
    subparsers = [
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)  # noqa: SLF001
    ]
    assert len(subparsers) == 1
    assert set(subparsers[0].choices) == set(COMMANDS), (
        f"only in parser {set(subparsers[0].choices) - set(COMMANDS)}, "
        f"only in COMMANDS {set(COMMANDS) - set(subparsers[0].choices)}"
    )

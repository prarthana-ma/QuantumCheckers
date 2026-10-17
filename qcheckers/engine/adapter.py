"""Seam for the upstream Cheqqers engine.

Owner: **Person B -- baseline agents and harness**, with **Person A** owning the
translation of upstream rules into :mod:`qcheckers.engine.protocol`.

Status: **NOT INTEGRATED -- by decision, not by omission.**
Gate 2's tag (`cog-paper-version`) is confirmed present upstream and the upstream
licence is confirmed AGPL-3.0 (read directly; see docs/REPRODUCIBILITY.md §8).
Because AGPL-3.0 is a strong copyleft, importing, wrapping or hosting upstream
code would carry source-sharing obligations disproportionate to a course pilot
whose results are honestly reported on the toy engine with documented
mismatches (docs/REPRODUCIBILITY.md §7). So this adapter stays a stub on
purpose: we do not vendor, wrap, or re-implement upstream code, and no
experiments depend on it. Revisit only with a deliberate re-licensing decision.

What has to happen before this file grows an implementation
------------------------------------------------------------
1. **Gate 2 -- version.** Pin the exact upstream commit or tag that matches the paper
   (brief section 3, Gate 2). Record the SHA in the reproducibility report.
2. **License.** Read the upstream ``LICENSE`` and record the conclusion (brief
   section 17). If it is AGPL-3.0 or another copyleft, decide before copying a single
   line whether to re-implement from the paper text instead of importing the code.
3. **Rule mapping.** Translate upstream state and move types onto
   :class:`~qcheckers.engine.protocol.GameEngine`, :class:`GameState` and the action
   union. Upstream representation of uncertainty is **UNVERIFIED**; if it uses complex
   amplitudes and phases, the toy engine's probability-only reading is a simplification
   and the viewer must say so.
4. **Legality parity tests.** Person A's legality tests must pass against both engines
   before any experiment number is reported.
5. **Measure cost.** Person B measures games-per-hour with the upstream engine
   (Gate 4); if it is too slow, cap board scope and document a reduced pilot.

Every method below raises rather than returning a plausible-looking wrong answer,
because a silently-wrong engine would poison every downstream statistic.
"""

from __future__ import annotations

from typing import Any, Sequence

from qcheckers.engine.protocol import Action, GameOutcome, GameState, Step

#: Upstream repository, recorded here so the pin is one edit away once Gate 2 passes.
UPSTREAM_REPO = "https://github.com/raatmarien/cheqqers"

#: Message every not-implemented path raises, so a traceback says what is missing.
GATE_2_MESSAGE = (
    "CheqqersAdapter is not implemented: the upstream Cheqqers engine has not been "
    "integrated. Gate 2 (paper-version tag) and the upstream license check are both "
    "still open, so this adapter raises instead of guessing. See "
    "qcheckers/engine/adapter.py and docs/quantum-checkers-project.md section 16. "
    f"Upstream repository: {UPSTREAM_REPO}"
)


class CheqqersAdapter:
    """Placeholder adapter that would expose the upstream engine as a ``GameEngine``.

    Implements the full :class:`~qcheckers.engine.protocol.GameEngine` surface so the
    type checker is satisfied and the call sites are already in place. Every method
    raises :class:`NotImplementedError`.

    Intended future signature (decided now so callers do not change later)::

        CheqqersAdapter(
            upstream_engine,
            *,
            seed: int,
            level: int | None = None,
            allow_observe: bool = False,
        )

    Parameters accepted for now
    ----------------------------
    seed:
        Retained and validated so that experiment code can be written against this
        class today. Unused.
    level, allow_observe:
        Retained to mirror :class:`GameEngine`. Unused.
    """

    name = "cheqqers-adapter"
    level = 0
    allow_observe = False
    max_plies = 0
    board_size = 0

    def __init__(
        self,
        *,
        seed: int = 0,
        level: int = 0,
        allow_observe: bool = False,
    ) -> None:
        if level not in (0, 1, 2):
            raise ValueError(f"level must be 0, 1 or 2; got {level!r}")
        self.seed = int(seed)
        self.level = level
        self.allow_observe = bool(allow_observe)

    def initial_state(self) -> GameState:
        raise NotImplementedError(GATE_2_MESSAGE)

    def legal_actions(self, state: GameState) -> tuple[Action, ...]:
        raise NotImplementedError(GATE_2_MESSAGE)

    def apply(self, state: GameState, action: Action) -> Step:
        raise NotImplementedError(GATE_2_MESSAGE)

    def is_terminal(self, state: GameState) -> bool:
        raise NotImplementedError(GATE_2_MESSAGE)

    def outcome(self, state: GameState) -> GameOutcome | None:
        raise NotImplementedError(GATE_2_MESSAGE)

    def render(self, state: GameState) -> dict[str, Any]:
        raise NotImplementedError(GATE_2_MESSAGE)

    @staticmethod
    def integration_checklist() -> Sequence[str]:
        """The exact steps that unblock this adapter, in order."""
        return (
            "Gate 2: pin the upstream commit or tag matching the paper version.",
            "Read the upstream LICENSE and record the conclusion (AGPL-3.0 suspected).",
            "Decide import-vs-reimplement before copying any upstream code.",
            "Translate upstream state and moves onto GameEngine and GameState.",
            "Pass Person A's legality tests against both engines.",
            "Measure games per hour before committing to a batch size (Gate 4).",
        )
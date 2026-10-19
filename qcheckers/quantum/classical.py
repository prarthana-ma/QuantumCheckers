"""Classical reference for the quantum layer (stdlib only, no qiskit).

This module reproduces, in plain Python, what the game engine does when it
"spreads" and "measures" — so the quantum circuits can be compared against it
numerically. It imports the engine's constants rather than duplicating them,
so the two cannot silently disagree about the weights.

What the comparison shows
-------------------------
The classical sampler's output does not depend on any phase — there is no
phase parameter anywhere in this module, because the engine has no phase.
The quantum interference circuit's output DOES depend on phase. That
dependence is the entire content of the project's quantum claim.
"""

from __future__ import annotations

import random

from qcheckers.engine.toy import SPREAD_ORIGIN_CHANCE, SPREAD_TAIL_CHANCE

#: The engine's standard three-square split: 0.5 at the origin, 0.5 shared
#: over the (up to) two diagonal targets.
CLASSICAL_SPLIT: dict[str, float] = {
    "00": SPREAD_ORIGIN_CHANCE,
    "01": SPREAD_TAIL_CHANCE / 2,
    "10": SPREAD_TAIL_CHANCE / 2,
    "11": 0.0,
}


def classical_split_sample(rng: random.Random) -> str:
    """One classical "measurement": ``random()`` vs cumulative weights.

    Mirrors ``DeterministicToyEngine._sample_sites``. Deliberately NOT a Born
    rule — there are no amplitudes here, only weights.
    """
    draw = rng.random()
    cumulative = 0.0
    for outcome in ("00", "01", "10"):
        cumulative += CLASSICAL_SPLIT[outcome]
        if draw < cumulative:
            return outcome
    return "10"


def classical_split_distribution() -> dict[str, float]:
    """The fixed classical distribution. Note the signature: no phase argument.

    There is nothing to vary. This constancy is what the interference circuit
    falsifies for the quantum case.
    """
    return dict(CLASSICAL_SPLIT)

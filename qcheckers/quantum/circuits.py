"""Genuine quantum circuits for the game's core mechanics.

Encoding
--------
One qubit per candidate square is wasteful for a demo, so a split over three
squares (origin + two forward diagonals, the archived toy engine's case) is encoded
in two qubits as computational-basis states::

    |00> = origin square      (target probability 0.5)
    |01> = first diagonal     (target probability 0.25)
    |10> = second diagonal    (target probability 0.25)
    |11> = unused             (target probability 0)

Bitstrings in counts follow Qiskit's little-endian convention: the rightmost
character is qubit 0.

How the split state is built (explicit gates, no ``initialize`` hiding)
-----------------------------------------------------------------------
Start from ``|00>``:

1. ``RY(pi/3)`` on qubit 1 gives ``sqrt(0.75)|0> + 0.5|1>``, i.e. the q1=0
   branch carries weight 0.75 and the q1=1 branch carries 0.25.
2. Controlled on q1=0, ``RY(theta2)`` on qubit 0 splits the q1=0 branch into
   2/3 vs 1/3, where ``theta2 = 2*acos(sqrt(2/3))``. The q1=1 branch is
   untouched.

Result: ``|00>`` with 0.75*2/3 = 0.5, ``|01>`` with 0.75*1/3 = 0.25,
``|10>`` with 0.25, ``|11>`` with 0. These are exactly the engine's
``SPREAD_ORIGIN_CHANCE`` / ``SPREAD_TAIL_CHANCE`` weights, but as squared
amplitudes of a real superposition rather than as classical weights.

Simplifications vs the full game (stated plainly)
--------------------------------------------------
* The demo fixes three candidate squares. The archived toy engine's spread supports one or
  two diagonal targets depending on board position; the construction generalises
  but only the three-square case is built here.
* Qubits stand in for squares abstractly. There is no board geometry, no turn
  order, no legality — those live in the engine. These circuits implement the
  *uncertainty primitive* (superposition + measurement), not the game.
* The interference circuit's recombine step (inverse preparation) is a physics
  demonstration, not the live game's merge gate. The live PaperQuantumEngine
  separately supports phase-sensitive merge and uses a two-target split with no
  residual source occupancy; this legacy three-site demonstration does not model it.
"""

from __future__ import annotations

import math

from qiskit import QuantumCircuit

#: Rotation putting weight 0.75 on q1=0 and 0.25 on q1=1:
#: cos^2(theta/2) = 0.75  =>  theta = pi/3.
_SPLIT_THETA1 = math.pi / 3

#: Rotation splitting the q1=0 branch into 2/3 vs 1/3:
#: cos^2(theta/2) = 2/3  =>  theta = 2*acos(sqrt(2/3)).
_SPLIT_THETA2 = 2.0 * math.acos(math.sqrt(2.0 / 3.0))

#: Target distribution (origin, diagonal 1, diagonal 2), mirroring
#: ``SPREAD_ORIGIN_CHANCE`` and ``SPREAD_TAIL_CHANCE`` in
#: ``qcheckers.engine.toy``. The fourth basis state must stay empty.
TARGET_DISTRIBUTION: dict[str, float] = {
    "00": 0.5,
    "01": 0.25,
    "10": 0.25,
    "11": 0.0,
}


def _prepare_split(qc: QuantumCircuit, q0: int = 0, q1: int = 1) -> None:
    """Apply the split-state preparation in place (no measurement).

    After this, the two-qubit state is
    ``sqrt(0.5)|00> + 0.5|01> + 0.5|10> + 0|11>``.
    """
    qc.ry(_SPLIT_THETA1, q1)
    # Controlled-on-|0>: flip the control, apply, flip back.
    qc.x(q1)
    qc.cry(_SPLIT_THETA2, q1, q0)
    qc.x(q1)


def _unprepare_split(qc: QuantumCircuit, q0: int = 0, q1: int = 1) -> None:
    """Inverse of :func:`_prepare_split`, in place.

    If the state between preparation and un-preparation acquired no relative
    phase, this returns the register exactly to ``|00>``. Any relative phase
    leaks amplitude into other basis states — that leakage IS the interference
    signal.
    """
    qc.x(q1)
    qc.cry(-_SPLIT_THETA2, q1, q0)
    qc.x(q1)
    qc.ry(-_SPLIT_THETA1, q1)


def split_circuit() -> QuantumCircuit:
    """The game's Split as a real superposition, then measured.

    Corresponds to the engine's ``SpreadAction`` with two diagonal targets:
    measuring this circuit samples origin/diagonal-1/diagonal-2 with
    probabilities 0.5/0.25/0.25 by the Born rule, exactly the weights the
    engine assigns classically.
    """
    qc = QuantumCircuit(2, 2)
    _prepare_split(qc)
    qc.measure([0, 1], [0, 1])
    return qc


def observe_circuit() -> QuantumCircuit:
    """The game's Observe as a single Born-rule measurement.

    Corresponds to the engine's ``ObserveAction``: one shot collapses the
    spread state onto a single definite square. Repeated over many shots the
    outcomes converge on the split distribution — that convergence is asserted
    in the test suite, and it is what makes this a measurement rather than a
    classical draw.
    """
    qc = QuantumCircuit(2, 2)
    _prepare_split(qc)
    qc.measure([0, 1], [0, 1])
    return qc


def interference_circuit(phase: float) -> QuantumCircuit:
    """Prepare, phase-shift one branch, recombine, measure.

    A relative phase ``phase`` is applied to the q0=1 subspace (a ``P`` gate
    on qubit 0), then the preparation is inverted. At ``phase = 0`` the
    register returns exactly to ``|00>`` — a coherence check no classical
    mixture can pass, because a mixture that was sampled early has no phase
    to preserve and un-computing it cannot restore ``|00>``.

    As ``phase`` varies, the output distribution changes. The classical engine
    has no phase parameter at all, so its output is *constant* in ``phase``.
    The quantum output is a non-constant function of ``phase``. That
    dependence — not any single distribution — is the proof that the quantum
    layer contains something the classical model cannot represent.
    """
    qc = QuantumCircuit(2, 2)
    _prepare_split(qc)
    qc.p(phase, 0)
    _unprepare_split(qc)
    qc.measure([0, 1], [0, 1])
    return qc


#: Phases swept by the demo runner and the interference test.
INTERFERENCE_PHASES: tuple[float, ...] = (0.0, math.pi / 2, math.pi)

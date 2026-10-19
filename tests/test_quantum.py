"""Tests for the real-quantum layer.

All offline (Aer simulator only). No credentials, no network.

The test that carries the project's quantum claim is
``test_interference_depends_on_phase``: it asserts the output distribution is
a NON-CONSTANT function of phase, which the classical model — having no phase
parameter at all — cannot reproduce.
"""

from __future__ import annotations

import math
import random

from qcheckers.quantum import circuits
from qcheckers.quantum.classical import (
    CLASSICAL_SPLIT,
    classical_split_distribution,
    classical_split_sample,
)
from qcheckers.quantum.validate import run_counts, run_probabilities

_SPLIT_SHOTS = 4000
_INTERFERENCE_SHOTS = 4000


def _assert_close(actual: float, expected: float, tol: float, label: str) -> None:
    assert abs(actual - expected) <= tol, f"{label}: {actual} != {expected} (+/- {tol})"


def test_split_matches_engine_weights():
    """The split circuit measures ~0.5/0.25/0.25, the engine's own weights."""
    probs = run_probabilities(circuits.split_circuit(), _SPLIT_SHOTS)
    for outcome, expected in circuits.TARGET_DISTRIBUTION.items():
        _assert_close(probs.get(outcome, 0.0), expected, 0.03, f"split {outcome}")
    # The unused basis state must stay (nearly) empty.
    assert probs.get("11", 0.0) < 0.01


def test_split_matches_classical_target():
    """Quantum and classical agree on the split — the overlap both must cover."""
    probs = run_probabilities(circuits.split_circuit(), _SPLIT_SHOTS)
    for outcome, expected in CLASSICAL_SPLIT.items():
        _assert_close(probs.get(outcome, 0.0), expected, 0.03, f"agree {outcome}")


def test_observe_converges_on_split_distribution():
    """Born rule: many single-shot measurements converge on the distribution."""
    probs = run_probabilities(circuits.observe_circuit(), _SPLIT_SHOTS)
    for outcome, expected in circuits.TARGET_DISTRIBUTION.items():
        _assert_close(probs.get(outcome, 0.0), expected, 0.03, f"observe {outcome}")


def test_probabilities_are_sane():
    """Probabilities sum to 1 and none are negative."""
    probs = run_probabilities(circuits.split_circuit(), _SPLIT_SHOTS)
    assert abs(sum(probs.values()) - 1.0) < 1e-9
    assert all(p >= 0.0 for p in probs.values())


def test_classical_has_no_phase_dependence():
    """The classical reference is constant: there is no phase to vary.

    This pins the negative claim. If the engine ever gains a phase parameter,
    this test must be rewritten — and the interference claim re-examined.
    """
    first = classical_split_distribution()
    second = classical_split_distribution()
    assert first == second == CLASSICAL_SPLIT
    rng = random.Random(7)
    samples = {classical_split_sample(rng) for _ in range(200)}
    assert samples <= {"00", "01", "10"}


def test_interference_returns_to_origin_at_zero_phase():
    """Coherence check: prepare, no phase, unprepare -> |00> deterministically.

    A classical mixture sampled early cannot pass this: once sampled, the
    phase information is gone and un-computing cannot restore |00>.
    """
    probs = run_probabilities(circuits.interference_circuit(0.0), _INTERFERENCE_SHOTS)
    assert probs.get("00", 0.0) > 0.99, f"P(|00>) at phase 0: {probs}"


def test_interference_depends_on_phase():
    """THE quantum claim: output is a non-constant function of phase.

    The classical model has no phase parameter, so its output is constant in
    phase by construction (see test_classical_has_no_phase_dependence). Here
    P(|00>) at phase=pi must differ materially from P(|00>) at phase=0.
    """
    p0 = run_probabilities(circuits.interference_circuit(0.0), _INTERFERENCE_SHOTS).get("00", 0.0)
    p_pi = run_probabilities(circuits.interference_circuit(math.pi), _INTERFERENCE_SHOTS).get("00", 0.0)
    assert abs(p_pi - p0) > 0.2, f"phase did nothing: P00(0)={p0}, P00(pi)={p_pi}"


def test_counts_shape():
    """Raw counts come back keyed by two-bit bitstrings."""
    counts = run_counts(circuits.split_circuit(), 500)
    assert sum(counts.values()) == 500
    assert set(counts) <= {"00", "01", "10", "11"}

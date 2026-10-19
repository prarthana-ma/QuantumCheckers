"""Turn a live game collapse distribution into a real measurement circuit.

The *live* game's collapse distributions (``qcheckers.engine.toy``) are encoded into a
Qiskit circuit that is submitted to IBM Quantum hardware, and the measured bitstring is
mapped back to the square that is written into game state.

Encoding
--------
A piece's spread is a distribution over ``N`` candidate squares (``N`` is 2 or 3 in
the engine today: origin + one or two forward diagonals, or the two squares a merge
produces). We need ``q = ceil(log2 N)`` qubits:

* ``N = 2`` -> 1 qubit -> ``|0>`` = site 0, ``|1>`` = site 1.
* ``N = 3`` -> 2 qubits -> ``|00>`` = site 0, ``|01>`` = site 1, ``|10>`` = site 2,
  and ``|11>`` is **unused** (target probability 0).

Bitstrings follow Qiskit's convention: the rightmost character is qubit 0, so the
integer index of a measured key is its plain base-2 value.

The state is prepared by :meth:`~qiskit.QuantumCircuit.initialize` with real
amplitudes ``sqrt(chance)`` per basis state. The game path needs every ``N`` and every
weight, so it builds the amplitude vector directly.

Invalid / noisy outcomes
------------------------
``shots = 1`` on real hardware can return any basis state, including the unused one.
The live sampler REFUSES such an outcome (:class:`server.quantum_measure.QuantumMeasurementError`
with code ``quantum_invalid_outcome``); nothing is substituted -- no simulator, no RNG.
"""

from __future__ import annotations

import math
from typing import Sequence

from qiskit import QuantumCircuit

#: A square, ``(row, col)``.
Square = tuple[int, int]

#: One ``(square, chance)`` entry of a spread distribution.
Site = tuple[Square, float]


def qubits_for(site_count: int) -> int:
    """Qubits needed to index ``site_count`` candidate squares (at least one).

    ``site_count = 2`` -> 1, ``3`` -> 2, ``4`` -> 2, ``5`` -> 3. Uses integer
    arithmetic (``bit_length``) rather than ``log2`` so it is exact for every size.
    """
    if site_count < 2:
        raise ValueError(f"a collapse needs at least 2 sites; got {site_count!r}")
    return (site_count - 1).bit_length()


def _normalised_amplitudes(sites: Sequence[Site], qubits: int) -> list[float]:
    """``sqrt(chance)`` per basis state, padded with zeros, renormalised.

    The engine already asserts the weights sum to 1.0; renormalising here defends the
    circuit against a caller passing a distribution that is only numerically close.
    """
    amplitudes = [0.0] * (2**qubits)
    for index, (_square, chance) in enumerate(sites):
        amplitudes[index] = math.sqrt(max(float(chance), 0.0))
    norm = math.sqrt(sum(amplitude * amplitude for amplitude in amplitudes))
    if norm <= 0.0:  # pragma: no cover - a Piece guarantees a positive total
        raise ValueError("cannot measure an all-zero distribution")
    return [amplitude / norm for amplitude in amplitudes]


def build_measurement_circuit(sites: Sequence[Site]) -> tuple[QuantumCircuit, dict[str, Square]]:
    """Build the measurement circuit for ``sites`` and its bitstring -> square map.

    Returns ``(circuit, mapping)`` where ``mapping`` keys are the get_counts bitstrings
    that correspond to real candidate squares. Any bitstring absent from ``mapping`` is
    an invalid/noisy outcome: it is unusable and the live sampler refuses it.
    """
    if len(sites) < 2:
        raise ValueError(f"a collapse needs at least 2 sites; got {len(sites)!r}")
    qubits = qubits_for(len(sites))
    circuit = QuantumCircuit(qubits, qubits)
    circuit.initialize(_normalised_amplitudes(sites, qubits))
    circuit.measure(range(qubits), range(qubits))
    mapping = {
        format(index, f"0{qubits}b"): square for index, (square, _chance) in enumerate(sites)
    }
    return circuit, mapping


__all__ = [
    "Site",
    "Square",
    "build_measurement_circuit",
    "qubits_for",
]

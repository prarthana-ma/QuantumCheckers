"""Offline Aer validation runner (no credentials, no network).

Every function here runs on the local ``AerSimulator``. The hardware-submission
step, when it happens, reuses the same circuit constructors from
:mod:`qcheckers.quantum.circuits` but is NOT part of this module.
"""

from __future__ import annotations

from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

_SIMULATOR = AerSimulator()


def run_counts(circuit: QuantumCircuit, shots: int) -> dict[str, int]:
    """Run one circuit on Aer and return raw counts keyed by bitstring."""
    result = _SIMULATOR.run(circuit, shots=shots).result()
    return dict(result.get_counts(circuit))


def run_probabilities(circuit: QuantumCircuit, shots: int) -> dict[str, float]:
    """Run one circuit on Aer and return empirical probabilities."""
    counts = run_counts(circuit, shots)
    return {outcome: count / shots for outcome, count in counts.items()}

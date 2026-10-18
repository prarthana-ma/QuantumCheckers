"""Offline demo runner: quantum vs classical, printed as a comparison table.

Uses IBM Quantum when a server-side API key is configured, otherwise local Aer.

Usage: ``python -m qcheckers.quantum``.
"""

from __future__ import annotations

from qcheckers.quantum import circuits
from qcheckers.quantum.classical import classical_split_distribution
from qcheckers.quantum.execution import execute_circuits

_SHOTS = 4000


def _row(label: str, probs: dict[str, float]) -> str:
    cells = "  ".join(f"{outcome}={probs.get(outcome, 0.0):.3f}" for outcome in ("00", "01", "10", "11"))
    return f"{label:<28} {cells}"


def main() -> None:
    batch = [circuits.split_circuit(), *[circuits.interference_circuit(phase) for phase in circuits.INTERFERENCE_PHASES]]
    execution = execute_circuits(batch, _SHOTS)
    print(f"backend: {execution.backend}")
    if execution.fallback_reason:
        print(f"fallback: {execution.fallback_reason}")
    probabilities = [{key: count / _SHOTS for key, count in counts.items()} for counts in execution.counts]
    print("== split: quantum vs classical (engine weights) ==")
    print(_row("classical target", classical_split_distribution()))
    print(_row("quantum measured", probabilities[0]))
    print()
    print("== interference sweep: P(|00>) after prepare/phase/unprepare ==")
    print("(classical answer is constant: it has no phase parameter)")
    for phase, probs in zip(circuits.INTERFERENCE_PHASES, probabilities[1:]):
        print(_row(f"phase={phase:.4f}", probs))
    print()
    print("== raw counts (split) ==")
    print(execution.counts[0])


if __name__ == "__main__":
    main()

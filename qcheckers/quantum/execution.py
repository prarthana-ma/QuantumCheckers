"""Optional IBM Quantum execution with an offline Aer fallback.

Credentials are read from the environment only and never saved or returned.
The live game uses PaperQuantumEngine; this runner executes the independent
circuit demonstration, not the persistent board state.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Sequence

from qiskit import QuantumCircuit

from qcheckers.quantum.validate import run_counts


@dataclass(frozen=True)
class ExecutionResult:
    backend: str
    counts: tuple[dict[str, int], ...]
    fallback_reason: str | None = None


def _run_ibm(circuits: Sequence[QuantumCircuit], shots: int, token: str) -> ExecutionResult:
    # Optional dependency: a missing IBM SDK must not break offline use.
    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

    instance = os.environ.get("IBM_QUANTUM_INSTANCE", "").strip()
    service = QiskitRuntimeService(
        channel="ibm_quantum_platform", token=token,
        **({"instance": instance} if instance else {"plans_preference": ["open"]}),
    )
    backend_name = os.environ.get("IBM_QUANTUM_BACKEND", "").strip()
    backend = service.backend(backend_name) if backend_name else service.least_busy(
        operational=True, simulator=False, min_num_qubits=2,
    )
    manager = generate_preset_pass_manager(backend=backend, optimization_level=1)
    job = SamplerV2(mode=backend).run([manager.run(circuit) for circuit in circuits], shots=shots)
    try:
        result = job.result(timeout=120)
        counts = tuple(dict(pub.data.c.get_counts()) for pub in result)
    except Exception:
        try:
            job.cancel()
        except Exception:
            pass
        raise
    return ExecutionResult(f"IBM Quantum ({backend.name})", counts)


def execute_circuits(circuits: Sequence[QuantumCircuit], shots: int = 4000) -> ExecutionResult:
    """Use IBM when configured; otherwise simulate locally without a network call.

    Missing SDK, invalid credentials, unavailable hardware, or a failed/slow job
    also fall back. Exception text is deliberately omitted because provider errors
    can contain credential or account details.
    """
    if shots <= 0:
        raise ValueError("shots must be positive")
    token = (os.environ.get("IBM_CLOUD_API_KEY") or os.environ.get("IBM_QUANTUM_API_KEY") or "").strip()
    reason = "IBM API key is not configured"
    if token:
        try:
            return _run_ibm(circuits, shots, token)
        except Exception as error:
            reason = f"IBM execution unavailable ({type(error).__name__})"
    return ExecutionResult("local Aer simulator", tuple(run_counts(circuit, shots) for circuit in circuits), reason)

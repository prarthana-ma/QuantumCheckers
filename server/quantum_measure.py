"""IBM Quantum hardware sampler for *live* game collapses.

This is the only hardware path. A missing key, instance or backend, or a failed or
timed-out job, raises :class:`QuantumMeasurementError` and the room is left exactly as
it was. An unusable (non-candidate) bitstring is refused with code
``quantum_invalid_outcome``. Never a silent Aer or RNG substitution.

One shot is submitted per collapse. The returned bitstring is mapped to a candidate
square by :mod:`qcheckers.quantum.game_measure`.

Credential hygiene: the token is read from the environment, held on this object, and
never placed in an exception message, a log line or a view payload. Provider exceptions
are swallowed and re-raised as a message that carries only the exception *type*.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

# Load .env file if present, unless a test session asked to skip it.
if os.environ.get("QCHECKERS_SKIP_DOTENV") not in ("1", "true", "yes"):
    try:
        from dotenv import load_dotenv
        # Look for .env in the project root (parent of server/)
        project_root = Path(__file__).parent.parent
        load_dotenv(project_root / ".env")
    except ImportError:
        pass  # python-dotenv not installed, rely on environment variables only

#: Default seconds to wait for a hardware job result before giving up. The wait runs in
#: a worker thread (see :mod:`server.app`), so it never blocks the event loop.
DEFAULT_JOB_TIMEOUT = 180.0

Square = tuple[int, int]
Site = tuple[Square, float]
Counts = Mapping[str, int]

#: A runner submits one circuit and returns ``(backend_name, job_id, counts)``. It is a
#: parameter so tests can mock the hardware boundary without a real QPU.
Runner = Callable[..., "tuple[str, str, Counts]"]


class QuantumMeasurementError(RuntimeError):
    """A live collapse could not be resolved on hardware.

    The room catches this and refuses the move, leaving game state untouched. ``code`` is
    the machine-readable protocol error code the client sees.
    """

    def __init__(self, message: str, code: str = "quantum_unavailable") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Provenance:
    """What actually produced one sampled square: the hardware trail, made visible.

    Records the backend and job that resolved the collapse, the raw measured
    bitstring and the candidate square it mapped to, alongside the pre-collapse
    distribution. There is no token or account detail here.
    """

    backend: str
    job_id: str
    bitstring: str
    sampled: Square
    probability: float
    sites: tuple[Site, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "job_id": self.job_id,
            "bitstring": self.bitstring,
            "sampled": list(self.sampled),
            "probability": self.probability,
            "sites": [[list(square), weight] for square, weight in self.sites],
        }


def _run_ibm_measurement(
    circuit: Any,
    shots: int,
    *,
    token: str,
    instance: str = "",
    backend_name: str = "",
    timeout: float = DEFAULT_JOB_TIMEOUT,
) -> tuple[str, str, Counts]:
    """Submit one circuit to IBM hardware; return ``(backend, job_id, counts)``.

    Kept as a module-level function so tests can monkeypatch the whole hardware boundary.
    Exception text is never propagated by callers: provider errors can carry account or
    credential detail.
    """
    # Optional dependency: imported lazily so the server stays importable without the IBM
    # SDK (the default offline game never reaches this function).
    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

    service = QiskitRuntimeService(
        channel="ibm_quantum_platform",
        token=token,
        **({"instance": instance} if instance else {"plans_preference": ["open"]}),
    )
    backend = (
        service.backend(backend_name)
        if backend_name
        else service.least_busy(operational=True, simulator=False, min_num_qubits=2)
    )
    isa_circuit = generate_preset_pass_manager(
        backend=backend, optimization_level=1
    ).run(circuit)
    job = SamplerV2(mode=backend).run([isa_circuit], shots=shots)
    try:
        result = job.result(timeout=timeout)
        counts: Counts = dict(result[0].data.c.get_counts())
    except Exception:
        try:
            job.cancel()
        except Exception:  # pragma: no cover - best-effort cleanup
            pass
        raise
    return backend.name, job.job_id(), counts


def _dominant_bitstring(counts: Counts) -> str:
    """The single measured bitstring, chosen deterministically.

    One shot means one key; if a provider ever returns more, the highest count wins and
    ties break lexicographically, so the choice never depends on dict order.
    """
    if not counts:
        raise QuantumMeasurementError("IBM Quantum returned no measurement outcome")
    return max(sorted(counts), key=lambda key: (counts[key], key))


class IBMHardwareSampler:
    """Blocking hardware sampler injected into a live room's engine.

    Call :func:`sampler_from_env` to build one from configuration; pass ``runner`` in
    tests to replace the QPU with a stub. Each call performs exactly one hardware
    measurement and stores the resulting :class:`Provenance` on :attr:`last`.
    """

    def __init__(
        self,
        *,
        token: str,
        instance: str = "",
        backend_name: str = "",
        shots: int = 1,
        timeout: float = DEFAULT_JOB_TIMEOUT,
        runner: Runner | None = None,
    ) -> None:
        if not token.strip():
            raise QuantumMeasurementError("IBM Quantum token is not configured")
        if isinstance(shots, bool) or shots != 1:
            raise QuantumMeasurementError(
                "IBM Quantum live collapses require exactly one shot",
                code="quantum_configuration_error",
            )
        try:
            resolved_timeout = float(timeout)
        except (TypeError, ValueError, OverflowError):
            raise QuantumMeasurementError(
                "IBM Quantum timeout must be a positive finite number",
                code="quantum_configuration_error",
            ) from None
        if not math.isfinite(resolved_timeout) or resolved_timeout <= 0:
            raise QuantumMeasurementError(
                "IBM Quantum timeout must be a positive finite number",
                code="quantum_configuration_error",
            )
        self._token = token.strip()
        self._instance = instance.strip()
        self._backend_name = backend_name.strip()
        self.shots = 1
        self._timeout = resolved_timeout
        self._runner: Runner = runner if runner is not None else _run_ibm_measurement
        self.last: Provenance | None = None
        self._resolved_backend: str | None = None

    @property
    def backend_label(self) -> str:
        """Best-known backend name: the resolved device, else the configured one."""
        return self._resolved_backend or self._backend_name or "IBM Quantum (unresolved)"

    def __call__(self, sites: Sequence[Site]) -> tuple[Square, float]:
        from qcheckers.quantum.game_measure import build_measurement_circuit

        # ``sites`` arrives as a tuple from the engine; normalise so provenance and the
        # circuit always describe the same, immutable distribution.
        frozen: tuple[Site, ...] = tuple((tuple(square), float(weight)) for square, weight in sites)
        circuit, mapping = build_measurement_circuit(frozen)
        try:
            backend, job_id, counts = self._runner(
                circuit,
                self.shots,
                token=self._token,
                instance=self._instance,
                backend_name=self._backend_name,
                timeout=self._timeout,
            )
        except QuantumMeasurementError:
            raise
        except Exception as error:
            # Deliberately only the exception type: provider text can leak the token.
            raise QuantumMeasurementError(
                f"IBM Quantum measurement unavailable ({type(error).__name__})"
            ) from None

        self._resolved_backend = backend
        bitstring = _dominant_bitstring(counts)
        square = mapping.get(bitstring)
        if square is None:
            raise QuantumMeasurementError(
                f"IBM Quantum returned an unusable measurement outcome ({bitstring!r}); "
                "the collapse was refused",
                code="quantum_invalid_outcome",
            )
        weight = next((w for s, w in frozen if s == square), 0.0)
        self.last = Provenance(
            backend=backend,
            job_id=job_id,
            bitstring=bitstring,
            sampled=square,
            probability=weight,
            sites=frozen,
        )
        return square, weight


def sampler_from_env(
    *, runner: Runner | None = None
) -> IBMHardwareSampler | None:
    """Build a sampler when IBM hardware is configured, else ``None``.

    ``None`` is the signal that the room runs the ordinary offline game. Only
    ``QISKIT_IBM_TOKEN`` is accepted; legacy token names are ignored.
    ``IBM_QUANTUM_INSTANCE`` and ``IBM_QUANTUM_BACKEND`` refine the hardware path. No
    token means no hardware and no error -- the offline game is still fully playable.

    Never use a ``NEXT_PUBLIC_`` prefix for the token: that would inline it into the
    client bundle and publish it to every visitor.
    """
    token = os.environ.get("QISKIT_IBM_TOKEN", "").strip()
    if not token:
        return None
    timeout = os.environ.get("IBM_QUANTUM_TIMEOUT", "").strip()
    return IBMHardwareSampler(
        token=token,
        instance=os.environ.get("IBM_QUANTUM_INSTANCE", ""),
        backend_name=os.environ.get("IBM_QUANTUM_BACKEND", ""),
        timeout=timeout if timeout else DEFAULT_JOB_TIMEOUT,
        runner=runner,
    )


__all__ = [
    "DEFAULT_JOB_TIMEOUT",
    "IBMHardwareSampler",
    "Provenance",
    "QuantumMeasurementError",
    "sampler_from_env",
]

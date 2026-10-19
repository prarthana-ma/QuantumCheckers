"""Real-quantum layer for Quantum Checkers.

Why this package exists
-----------------------
The game engine (``qcheckers.engine.toy``) is classical probability only: its
"measurement" is ``random()`` against cumulative weights, and it has no
amplitudes, no phase, and no interference. That is indefensible as the quantum
content of a quantum-computing course project, so this package implements the
same game mechanics as genuine quantum circuits.

What lives here
---------------
* :mod:`qcheckers.quantum.circuits` — split, observe, and interference circuits.
* :mod:`qcheckers.quantum.classical` — the classical reference (stdlib only),
  mirroring the engine's constants so quantum and classical can be compared
  numerically.
* :mod:`qcheckers.quantum.validate` — Aer-backed validation runner, always offline.
* :mod:`qcheckers.quantum.execution` — optional IBM runner with local Aer fallback.

Execution configuration
-----------------------
The CLI uses IBM Quantum only when ``IBM_CLOUD_API_KEY`` (or
``IBM_QUANTUM_API_KEY``) is configured. Install ``requirements-ibm.txt`` for that
optional path. With no key, or when IBM is unavailable, it uses local Aer. The
game server continues using the documented toy engine in every configuration.

Honesty boundary
----------------
These are OUR circuits for OUR mechanics. They do not reproduce the upstream
Cheqqers paper's engine (not integrated, AGPL-3.0, deliberate decision — see
``docs/ATTRIBUTION.md``). Where a circuit simplifies the full game
mechanic, its docstring says exactly how.
"""

from __future__ import annotations

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
* :mod:`qcheckers.quantum.game_measure` — the real measurement circuit for live
  collapses. The hardware transport is :mod:`server.quantum_measure`.

Execution configuration
-----------------------
There are exactly two modes:

1. No ``QISKIT_IBM_TOKEN``: the offline toy engine runs. No simulator is used.
2. ``QISKIT_IBM_TOKEN`` set: every collapse submits one shot of a real measurement
   circuit to IBM Quantum. ``IBM_QUANTUM_INSTANCE``, ``IBM_QUANTUM_BACKEND`` and
   ``IBM_QUANTUM_TIMEOUT`` are optional, and ``QCHECKERS_DISABLE_HARDWARE`` is the
   off-switch. A failed job or an unusable outcome refuses the move and leaves the
   state unchanged.

``requirements-ibm.txt`` is still needed for hardware mode.

Honesty boundary
----------------
These are OUR circuits for OUR mechanics. They do not reproduce the upstream
Cheqqers paper's engine (not integrated, AGPL-3.0, deliberate decision — see
``docs/ATTRIBUTION.md``). Where a circuit simplifies the full game
mechanic, its docstring says exactly how.
"""

from __future__ import annotations

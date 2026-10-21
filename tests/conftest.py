"""Test defaults: never let a developer's local .env reach IBM Quantum.

The server loads .env at import time. During tests we skip that load and
clear any IBM variables from the shell, so only the fake credentials set by
individual tests are visible.
"""

import os

os.environ["QCHECKERS_SKIP_DOTENV"] = "1"
for _name in (
    "QISKIT_IBM_TOKEN",
    "IBM_QUANTUM_INSTANCE",
    "IBM_QUANTUM_BACKEND",
    "IBM_QUANTUM_TIMEOUT",
):
    os.environ.pop(_name, None)

"""qcheckers -- harness for the Quantum Checkers reproduction-plus-extension study.

Owner of this package: shared foundation. Every module docstring names the person
role (Person A..E, see ``docs/TEAM.md``) that owns the file.

Nothing in this package imports a quantum SDK. The upstream Cheqqers engine is not
integrated yet (Gate 2 pending), so the experiments currently run against the
deterministic :mod:`qcheckers.engine.toy` stand-in engine.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
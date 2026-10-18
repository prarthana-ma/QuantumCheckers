"""Credential selection and fallback keep the circuit demo usable offline."""
from qcheckers.quantum import circuits, execution


def test_missing_key_simulates_without_calling_ibm(monkeypatch):
    monkeypatch.delenv("IBM_CLOUD_API_KEY", raising=False)
    monkeypatch.delenv("IBM_QUANTUM_API_KEY", raising=False)
    def forbidden(*args):
        raise AssertionError("offline execution contacted IBM")
    monkeypatch.setattr(execution, "_run_ibm", forbidden)
    result = execution.execute_circuits([circuits.split_circuit()], shots=128)
    assert result.backend == "local Aer simulator"
    assert sum(result.counts[0].values()) == 128
    assert result.counts[0].get("11", 0) == 0


def test_ibm_failure_falls_back_without_exposing_key(monkeypatch):
    monkeypatch.setenv("IBM_CLOUD_API_KEY", "private-test-token")
    def unavailable(*args):
        raise RuntimeError("provider error: private-test-token")
    monkeypatch.setattr(execution, "_run_ibm", unavailable)
    result = execution.execute_circuits([circuits.interference_circuit(0)], shots=128)
    assert result.backend == "local Aer simulator"
    assert result.counts == ({"00": 128},)
    assert "private-test-token" not in result.fallback_reason

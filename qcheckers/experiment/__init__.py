"""Experiment layer: record schema, seeded runner, statistics, configuration.

Ownership:

* :mod:`schema` -- **Person B** (log format is part of the harness contract).
* :mod:`runner` -- **Person B**.
* :mod:`stats` -- **Person D**.
* :mod:`config` -- **Person D**, with **Person B** for the fields the runner reads.
"""

from qcheckers.experiment.config import (
    CONDITIONS,
    ConditionConfig,
    ExperimentConfig,
)
from qcheckers.experiment.runner import (
    append_jsonl,
    play,
    run_condition,
    write_jsonl,
)
from qcheckers.experiment.schema import GameRecord, TurnRecord
from qcheckers.experiment.stats import (
    Rate,
    compare_rates,
    summarize,
    wilson_interval,
)

__all__ = [
    "CONDITIONS",
    "ConditionConfig",
    "ExperimentConfig",
    "GameRecord",
    "Rate",
    "TurnRecord",
    "append_jsonl",
    "compare_rates",
    "play",
    "run_condition",
    "summarize",
    "wilson_interval",
    "write_jsonl",
]
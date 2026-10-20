"""Agents for the Quantum Checkers study.

Ownership:

* :mod:`base` -- **Person B**, with :class:`Agent` as the shared interface.
* :mod:`random_agent` -- **Person B**. Matched random baseline.
* :mod:`mcts_baseline` -- **Person B**. Tree-search baseline: UCT selection, seeded
  rollouts and the static evaluation are complete and tested. Upstream-engine
  integration is intentionally out of scope.
* :mod:`observe_agent`, :mod:`prob_aware` -- **Person C**. The candidate extension.
  Both carry a ``NOVELTY PENDING GATE 5`` marker; neither is a validated finding.
"""

from qcheckers.agents.base import Agent
from qcheckers.agents.mcts_baseline import MCTSBaselineAgent, uct_score
from qcheckers.agents.observe_agent import ObserveAgent
from qcheckers.agents.prob_aware import ProbAwareAgent
from qcheckers.agents.random_agent import RandomAgent

__all__ = [
    "Agent",
    "MCTSBaselineAgent",
    "ObserveAgent",
    "ProbAwareAgent",
    "RandomAgent",
    "uct_score",
]

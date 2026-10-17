# QuantumCheckers

Quantum Checkers — a checkers variant with quantum-inspired mechanics (splits, merges,
measurement) evaluated with seeded, reproducible agent experiments.

This is the team's working repository for the current phase: each part lands on its own
branch and merges into `main` through a pull request.

## Parts

- **P1** — AI agents and search: observe policy, probability-aware search, ablation runs.
- **P2** — Statistics and experimental design: metrics, confidence intervals, figures.
- **P3** — Baselines, runner and verification: random/MCTS baselines, seeded runs, logs.
- **P4** — Replay viewer and visualization: interactive replay and experiment figures.
- **P5** — Quantum rules and engine: game rules, engine, adapter, engine tests.

## Workflow

1. Clone this repository.
2. Branch off `main`: `git switch -c p1/short-topic`.
3. Add only the files for your part; leave other parts' paths untouched.
4. Push the branch and open a pull request into `main`.

```sh
git clone https://github.com/prarthana-ma/QuantumCheckers.git
cd QuantumCheckers
git switch -c p1/observe-prob-agents
# add your own files, e.g.:
git add qcheckers/agents/observe_agent.py qcheckers/agents/prob_aware.py scripts/run_ablation.py
git commit -m "P1: observe agent, probability-aware search, ablation CLI"
git push -u origin p1/observe-prob-agents
```

This repository is the current-phase integration point; the wider project's full
development history lives in a private working repository.

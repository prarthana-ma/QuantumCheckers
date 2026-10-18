# How the game agents work

This project has two agent tracks. The older research agents remain frozen for
reproducibility with `DeterministicToyEngine`; their archived results belong only to
that 4×4 probability-only model. The local server now defaults to `PaperQuantumEngine`
and uses a separate live search agent. Neither the older agent results nor their
strength estimates transfer to the paper-based live rules.

The rules discussed below follow the paper's levels and MCTS description in Sections
III and V–VII of [Quantum Checkers](https://arxiv.org/pdf/2506.05962). The paper
reports empirical play against random agents. It does not establish a winning policy
for every level.

## Frozen research agents

`make_agent` in `qcheckers/experiment/runner.py` builds the experiment agents:

| Name | What the code does |
| --- | --- |
| `random` | Chooses uniformly from the supplied legal actions. |
| `mcts` | Uses `MCTSBaselineAgent`: 24 root-action UCT iterations by default, exploration constant √2, a two-ply shallow greedy reply, then up to 32 uniformly random rollout plies. |
| `observe` | Uses `ObserveAgent`: if an eligible own spread piece is at or below its observation threshold, observes the fuzziest one; otherwise falls back to a simple capture-preferring action. It does not search a tree. |
| `prob` | Uses `ProbAwareAgent` with 24 iterations, √2 exploration, a two-ply shallow reply and up to 32 rollout plies. Its rollout samples actions with weights derived from the piece's chance at the action origin or merge target. |
| `hard` | Uses `ProbAwareAgent` with an observation threshold of 0.5 and eager splitting. The demo policy takes an eligible Observe or first available spread action before invoking search in some positions. |

The MCTS agents store visit and value statistics for root actions. They do not retain a
full tree of successor positions. Each iteration selects a root action with UCT,
applies it, follows a small greedy reply sequence, then runs a seeded random rollout.
Terminal states receive win/loss/draw values; a rollout cutoff uses a static
probability-aware evaluation. In the current shallow implementation, increasing the
reply depth beyond the default has a limitation: the greedy reply routine minimizes
the root's score at every reply ply, including a later root turn. The default depth of
two only evaluates one reply from the opponent.

There are also known heuristic asymmetries in the frozen code. The row-progress term
in `mcts_baseline._advance_of` and `prob_aware.expected_evaluation` assigns Player 0's
home row the negative extreme instead of zero. The probability-aware evaluator also
adds progress per piece in addition to its chance-weighted piece value; this differs
from the baseline's smaller progress-only bonus. These details matter when reading
old experiment results, so the implementations are left unchanged.

## Live MCTS

`LiveMCTSAgent` in `qcheckers/agents/live_mcts.py` is a separate agent for a
`PaperQuantumEngine`-compatible engine. It stores a tree of state nodes. Each action
keeps separate child branches keyed by the sampled state returned by `engine.apply`,
so two outcomes of one stochastic action are not collapsed into one presumed result.
UCT uses root-player value throughout: it maximizes when the current state belongs to
the root player and minimizes when it belongs to the opponent. This is important when
a capture grants the same player another move.

Each live iteration follows the standard four MCTS stages:

1. **Selection:** choose an unvisited, unblocked action first. After that, choose the
   action with the highest
   `sign(state.turn, root_player) * Q(a) + √2 * √(ln(parent_visits) / action_visits)`.
   `Q(a)` is mean reward from the root player's perspective; the sign is +1 when the
   state belongs to the root player and −1 when it belongs to the opponent. Thus both
   players optimize their own side, including during a same-player capture continuation.
2. **Expansion:** apply the selected move and create a child for the resulting state.
   Different sampled outcomes of one stochastic action have separate child nodes keyed
   by the resulting state signature.
3. **Rollout:** from a newly expanded node, choose uniformly from legal actions until
   terminal, a depth limit, or the deterministic branch-work limit.
4. **Backpropagation:** send the root-perspective outcome or cutoff score back through
   the actions traversed by that iteration. At the root, return the action with the
   most visits; mean root reward breaks visit-count ties.

Terminal outcomes are scored as +1 for a root win, −1 for a root loss and 0 for a draw.
A depth cutoff uses expected material: each piece's site weights contribute according
to survival, with smaller king and normalized-advance terms. The score is bounded and
zero-sum; it does not add a separate penalty from the captured-piece history.

The agent defaults to 200 tree iterations, depth 8, at most 48 rollout plies, branch
work budget 1,024 and exploration constant √2. Paper-rules AI rooms use depth 4 and
rollout cap 8: Easy uses the random agent, Medium uses 200 iterations and Hard uses
400 iterations. Observe is offered only when the engine's rules allow it (Level 4);
the live agent searches the offered legal actions without the old Hard tier's forced
Observe or split demo choices. The agent clones the engine once per decision, resets a
private seeded RNG, and disables the clone's sampler. Search therefore uses the
engine's local stochastic transitions and does not schedule hardware sampler jobs.
Repeating a decision with the same seed and position produces the same choice.

The branch-work budget is deterministic rather than a wall-clock cutoff. Each
simulation can spend at most the larger of 1,024 branch units and the root state's
current amplitude-branch count. Applying a transition charges the source state's
branch count; rollout stops and evaluates the current state when its remaining budget
cannot pay for another step. A high-branch position therefore gets shorter simulated
continuations while still allowing one root action to be sampled per iteration.

On the 8×8 Level 2 initial position, one local benchmark measured the 4/8 room setting
at 1.76 seconds for Medium and 3.91 seconds for Hard. A 12-ply line favoring spread
reached three amplitude branches and measured 2.40 and 4.96 seconds. These are
environment-specific samples, not latency guarantees.

If a simulated transition exceeds the paper engine's branch cap, the search marks
that action unavailable in that search node and evaluates another available line. A
branch-capped root action is excluded from the final choice whenever another offered
action could be simulated. If every offered action exceeds the cap, the legal-action
contract still requires a fallback, so the agent returns the first offered action. The
server can then refuse that transition without changing state. `RetryAI` repeats the
same position with the same decision seed, so a deterministic cap failure persists; in
this all-actions-capped case the player needs to resign or start a new game.

This is a bounded stochastic tree search, not a minimax proof. Random rollouts,
finite iteration budgets and chance sampling can miss tactics. No agent has a proved
winning strategy for every level, and the old research agents' performance has not
been validated on the paper-based live engine.

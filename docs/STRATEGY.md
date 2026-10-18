# Practical strategy by level

These are heuristics for making decisions, not solved strategies. The game contains
stochastic measurement and, at higher levels, phase-sensitive interference. A line
that is favorable on average can still collapse against you. Neither the research
agents nor the new bounded live search has a proven winning strategy for every level
or a guarantee of beating even a random opponent in every round.

## What “winning strategy” means here

There is no honest claim of a forced win at every level. Standard 8×8 English draughts
(the Level 0 starting game) is weakly solved: perfect play by both sides draws. The
provable result is a drawing strategy, not a strategy that forces a win. A player can
win if the opponent makes a mistake. See Schaeffer et al., [Checkers Is Solved](https://doi.org/10.1126/science.1144079),
and the [Chinook solving project](https://webdocs.cs.ualberta.ca/~chinook/publications/solving_checkers.html).

Levels 1–3 add split moves, measurement, conditional capture and interference. The
paper reports initial experiments with random and MCTS agents, not a proof of the
optimal result from the starting position. Level 4 adds this project's own Observe and
decoherence rules, so it has no published solution either. The plans below are
practical ways to increase winning chances against fallible opponents; they are not
forced-win lines or guarantees. The local MCTS bot is a bounded sampled search, not
Chinook and not a perfect-play solver.

| Level | Best-supported claim | Practical objective |
| --- | --- | --- |
| 0 — Classical | Perfect play draws in standard English draughts. | Hold the draw when equal or behind; convert an opponent's error when ahead. |
| 1 — Superposition | No proven game-theoretic result. | Use useful, defensible branches; exploit risky capture attempts. |
| 2 — Entanglement | No proven game-theoretic result. | Create favorable capture/no-capture correlations and preserve a safe reply in each outcome. |
| 3 — Interference | No proven game-theoretic result. | Merge only when the resulting amplitudes and follow-up positions are favorable. |
| 4 — Project extension | Custom rules; no published solution or perfect-play result. | Manage observation tempo and the coherence clock; plan for collapse outcomes. |

## A practical plan for converting an advantage

At every level, build an advantage that survives the opponent's best reply, then
convert it without allowing a promotion or forced capture. Before moving, check
compulsory captures and capture chains; count surviving pieces and their probabilities;
locate safe promotion routes; and consider the opponent's best immediate capture. In
quantum positions, evaluate joint outcomes rather than treating each square's
probability as independent. When ahead, prefer safe exchanges and lower variance. When
behind, preserve counterplay and create multiple threats, accepting uncertainty only
when a quiet line is likely to lose anyway.

No fixed opening sequence is claimed as a winning line: a move depends on the board,
orientation, and opponent reply. Use the legal-action list and these checks to select a
plan for the current position.

The paper levels follow Sections III and V–VII of the primary
[Quantum Checkers paper](https://arxiv.org/pdf/2506.05962). Levels 0–3 are the paper's
classical, split, entanglement and interference stages. Level 4 is this project's
custom extension for decoherence/voluntary observation; do not present it as a
published level of the paper.

## A short decision routine

For each turn, use this order:

1. Enumerate the engine's legal actions. Check mandatory captures and any forced
   same-player continuation first.
2. Ask what each action can do across its possible states, not only at the most
   attractive square. Estimate both the payoff and the chance of each outcome.
3. Prefer moves that preserve useful continuations while denying the opponent an
   immediate capture. In Levels 0–3, measurement is triggered by the paper's capture
   rules; voluntary `Observe` is available only in this project's custom Level 4.
4. Re-evaluate after every collapse. The newly observed board can change which
   follow-up is safe.

For example, if a piece has equal amplitude on two candidate squares, a measurement
has a 1/2 chance of selecting either square. In Levels 1–3, that measurement occurs
when the capture rules call for it; in Level 4, a player may also choose Observe. An
attack tied to only one branch has a real chance of failing; treat it as a risk, not as
a certain capture.

## Level 0 — classical checkers

No split or phase mechanics are available. Use ordinary material, promotion and
forced-capture tactics.

**Winning goal:** Against perfect play from the standard start, aim to draw; there is
no forced win. Against an imperfect opponent, keep the position sound until they give
you a material, king or tempo advantage, then simplify safely and promote. If ahead,
trade only when the resulting ending remains favorable; if behind, avoid trades and
create a promotion race or forced tactic.

### Opening

- Advance connected pieces so they protect one another's landing squares.
- Keep a back-rank guard until you can see a safe route for an opposing king.
- Avoid moving a single edge piece far ahead of its support.

### Middlegame

- Before taking a capture, inspect the full forced sequence and the square where the
  capturing piece ends. A jump can expose it to a reply.
- Exchange when ahead in material or when the exchange removes a dangerous king.
- Use two pieces to cover the opponent's forward diagonals; isolated defenders are
  easy to lure into a forced trade.

### Endgame and counterplay

- Promote with a protected route. A king's extra mobility is often more valuable than
  one extra man in a crowded center.
- When behind, keep pieces separated and seek a promotion race or a forced fork rather
  than trading into a lost count.
- When defending, keep a king between the runner and promotion row and avoid giving
  the opponent a forced multi-jump.

## Level 1 — split and measurement

Splitting moves a piece into a superposition over candidate squares. Captures can
measure the relevant state; success depends on the piece occupying the required
locations. The paper also allows a split piece to be moved or split again.

**Winning goal:** Preserve a useful distribution without offering a high-value capture
measurement. Split to create a second threat or escape route, then keep both branches
safe and connected to a promotion plan. Attack a split opponent only after comparing
the capture and pass outcomes; choose lines where your position remains playable either
way. An ordinary move does not measure.

### Opening

- Split only when both branches have a purpose: for example, one branch supports a
  central advance while the other protects a threatened diagonal.
- Keep at least one certain piece near each likely landing area. A useful split is one
  that creates choices without leaving both branches immediately capturable.
- Avoid spreading every piece early. It increases the number of outcomes you must
  account for and can make a planned defense unreliable.

### Middlegame

- Track branch weights. If a piece occupies the jumped square with chance 0.5, an
  attack whose success requires that location has a 50% branch contribution before
  accounting for other conditions. Do not count it as a guaranteed removal.
- Target a split opponent when a successful collapse can remove it; keep an alternate
  move ready for the outcome where the target is elsewhere.
- Split to create threats on more than one diagonal, then use certain pieces to cover
  the opponent's responses. A branch with no follow-up is often wasted probability.

### Endgame and counterplay

- Favor a reliable route to promotion over a low-probability capture when pieces are
  few. A collapse can decide the game in either direction.
- If ahead, reduce exposure: prefer moves that leave the opponent one low-risk choice
  rather than several uncertain captures.
- If behind, preserve useful branches and look for a line that makes a capture attempt
  costly. In Levels 1–3, measurement follows capture rules; players cannot demand a
  voluntary measurement. Do not assume a split is safe simply because it cannot be
  captured on every branch.

## Level 2 — entanglement and conditional captures

Capturing a split defender can correlate the attacker's result with the defender's
location. This can turn what looks like a failed capture into a conditional outcome:
the piece is removed in the branches where the capture condition is met, while the
other branches preserve a correlated state. Think in joint outcomes rather than
independent piece probabilities.

**Winning goal:** Make both correlated capture outcomes favorable. Before trying to
capture a split defender, write down where the attacker and defender end in the capture
and non-capture branches. Prefer attempts where each branch wins material, improves
safety or leaves a useful threat. If one branch loses immediately, pressure the
opponent with another move instead.

### Opening

- Keep your own pieces supported before creating an entangled capture threat. A
  correlation is useful only if the resulting positions leave you a playable reply.
- Prefer threats that constrain the opponent's available moves across several
  branches. An opponent forced to respond in one place may give up another route.

### Middlegame

- Before attacking a split defender, list the conditional results: capture branch,
  non-capture branch, and the attacker's location in each. Evaluate the weakest
  resulting position, not only the branch where the capture succeeds.
- Use entanglement to make an opponent's best response costly. If every branch leaves
  a follow-up threat, the attack can be sound even when removal is not certain.
- Watch for your own correlation traps. A capture can leave the attacker entangled or
  displaced where a reply becomes available.

### Endgame and counterplay

- With few pieces, conditional removal can outweigh a modest material risk. Compare
  the chance-weighted gain against the branches where the opponent survives with a
  promotion route.
- Defend by occupying likely landing squares and keeping a second route open. The
  opponent may still produce a favorable conditional branch, but fewer follow-ups
  limits the damage.
- Do not evaluate a piece only by its marginal chance. The joint state with its
  entangled partner can determine which moves are legal or favorable.

## Level 3 — phase and interference

At this level, amplitudes carry phase. Merging branches of the same original piece
uses the inverse split operation and can interfere; it is not equivalent to choosing
one square or taking the union of possible locations. Relative phase can reinforce
some outcomes and cancel others.

**Winning goal:** Treat a merge as an amplitude transformation, not a probability
shortcut. Trace how the branches were created and moved, then evaluate the resulting
state and the opponent's best reply. Merge when interference improves the prospects
for a safe capture, escape or promotion; otherwise pursue a more predictable material
advantage.

### Opening

- Learn which split and inverse-merge paths are available from the current position.
  Record the phase and branch amplitudes when comparing two otherwise similar lines.
- Keep a conventional safe move available while experimenting. A theoretical
  interference gain is fragile if the opponent can force a different branch first.

### Middlegame

- Use a merge only when you can identify the amplitudes it recombines and the resulting
  interference pattern. Two branches reaching one destination do not automatically
  guarantee that the piece remains there.
- Preserve the same original piece identity across branches; interference requires
  those branches to be recombinable. Independent pieces do not become one piece just
  because they can reach the same square.
- Counter an opponent's prepared merge by changing the available path or forcing a
  measurement/capture before the branches can recombine.

### Endgame and counterplay

- Prefer a verified line over a speculative interference trick when a king route is
  already safe. Cancellation can remove an expected landing amplitude.
- In a tight ending, compare the final distribution after the merge with the
  distribution before it. Check whether the surviving branches leave a legal move and
  whether the opponent gets a capture.
- Against a branch-sensitive threat, disrupt one leg of the path rather than defending
  only the final target square.

## Level 4 — custom decoherence / observation extension

Level 4 in this project adds a custom time limit for spread states and an Observe
action. A spread piece that remains unmeasured can decohere after its configured
coherence interval; voluntary observation collapses it immediately and costs a turn.
These are project rules layered on top of the paper-based engine.

**Winning goal:** Spend an Observe turn only when the information changes your next
action enough to justify losing tempo. Before observing, plan a sound follow-up for
each possible result. Track decoherence timing and do not base a forced win on a branch
that may collapse before you can use it. When ahead, simplify and avoid needless
spreads; when behind, create threats that force the opponent to choose among bad
replies.

### Opening

- Split with a plan for the coherence clock. A branch that is useful for only one turn
  may be better observed or moved before it expires.
- Avoid creating more spread pieces than you can track. Their clocks can resolve in
  awkward positions at once.

### Middlegame

- Compare the cost of spending a turn on Observe with the risk of automatic
  decoherence. Observe when certainty unlocks a strong follow-up or prevents a
  dangerous capture; otherwise use the turn to improve the board.
- Count the remaining coherence turns explicitly. For instance, if a piece has one
  turn left, a plan requiring two future moves cannot rely on keeping both branches.
- Pressure an opponent's low-coherence spread pieces. They may have to act, observe or
  accept the automatic collapse before their preferred timing.

### Endgame and counterplay

- If ahead, use observation selectively to remove variance, but ensure the lost tempo
  does not let a runner promote.
- If behind, retain a favorable spread when its branches create useful threats, while
  planning around the forced decoherence result.
- When defending against an imminent collapse, keep a legal reply for either sampled
  square. A deadline makes the result predictable in timing, not in location.

## What can be claimed

These level-by-level plans are practical guidance, not a theorem or an engine strength
report. The paper's reported MCTS results are empirical and its discussion identifies
strategy and rollout valuation as open research questions. The live agent uses a
bounded UCT tree and sampled outcomes; it may miss rare but decisive branches. Results
from the old toy-engine agents should not be used as evidence for the new paper-based
engine without fresh, controlled evaluation.

# Quantum Checkers Project Brief

> **Initial project proposal (planning document).** Some gates and claims below are explicitly marked unverified because this brief predates the completed study. Current findings and decisions are recorded in [`REPORT.md`](REPORT.md) and [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md).

## How to read VERIFIED versus UNVERIFIED in this document

- **VERIFIED AS CANDIDATE-PROVIDED:** Means the text string was provided in the candidate brief for this project. It does not mean we independently opened, ran, or confirmed it while writing this file.
- **VERIFIED BY INDEPENDENT CHECK IN THIS FILE:** Means we directly checked it while writing this file and can describe how. Nothing in this version claims that level except the existence of this brief file itself.
- **UNVERIFIED:** Means it came from prior review, candidate claims, or general expectation, but was not independently confirmed while writing this file. Treat it as a lead to check, not a fact to cite.
- Rule used throughout: if a fact came from prior review but was not independently checked in this file, it is labeled **UNVERIFIED**.

This brief is standalone. It does not assume you have read the full paper. It is written for five CS undergraduates.

---

## 1. Project title and one-sentence pitch

**Project title:** Quantum Checkers: The Development and Analysis of a Quantum Combinatorial Game

**One-sentence pitch:** A checkers game where pieces can be in quantum-like uncertain states, plus a controlled study of whether players and AI agents should be allowed to voluntarily measure pieces to resolve that uncertainty.

> Status note: paper title above is **VERIFIED AS CANDIDATE-PROVIDED**. Whether the published version matches this exact title is **UNVERIFIED until the publisher page and final paper are read**.

---

## 2. Decision status: published-paper status and collision-safety caveat

**Decision status: HOLD FOR 48-HOUR KILL TEST - DO NOT COMMIT TO FULL BUILD YET.**

- Published-paper status is **UNVERIFIED**. The candidate states this is a published paper with a DOI, repository, and live site. The DOI string and links were provided, but final publication status, publisher page content, peer-review status, and whether the repository code matches the final-paper version remain to be independently confirmed.
- **Collision-safety caveat:** Because the paper is stated to be published and the code and demo are stated to be public, any work that only repeats the existing rules, engine, agents, or displays is not novel. It may also collide with follow-up work by the original authors or others. Our project is only safe if we keep reproduction small and add a clearly separate controlled study. See Sections 10, 11, 16, 17, and 18.
- Publisher-page, final-paper content, and live gameplay execution details remain to be independently confirmed. Nothing in this brief should be used as proof of publication or functionality.

---

## 3. Paper, DOI, repository, live demo, license, and version and code notes

- **Paper title:** Quantum Checkers: The Development and Analysis of a Quantum Combinatorial Game - **VERIFIED AS CANDIDATE-PROVIDED**, content **UNVERIFIED**.
- **DOI:** https://doi.org/10.1109/COG64752.2025.11114278 - **VERIFIED AS CANDIDATE-PROVIDED** as a string. Whether it resolves, whether it leads to the correct publisher page, whether that page shows final publication, and what the exact publication details are, are all **UNVERIFIED and to be confirmed in the 48-hour kill test**.
- **Repository:** https://github.com/raatmarien/cheqqers - **VERIFIED AS CANDIDATE-PROVIDED** as a string. Repository contents, branch state, version tags, license file, readme claims, engine behavior, and whether any tag corresponds to the paper version are all **UNVERIFIED**.
- **Live site:** https://cheqqers.com - **VERIFIED AS CANDIDATE-PROVIDED** as a string. Whether the site loads, whether gameplay works, what rules variant it runs, and what display features it currently shows are all **UNVERIFIED and require direct independent opening and play-testing**.
- **License:** **UNVERIFIED.** Do not assume a license. The repository license must be opened and read directly. Prior review suggested a strong copyleft license may apply, which would affect how we reuse, modify, and redistribute code. Until read directly, treat license implications as open risk. See Section 17.
- **Version and code notes:** **UNVERIFIED.** We do not list version numbers, commit identifiers, file names, folder structure, or install and run instructions here because those were not independently checked while writing this file. Inventing them would be misleading. The kill test must inspect whether the repository marks a paper-version tag or release, and whether the live site matches that version. If no paper-version marker exists, record that explicitly as a limitation.
- General rule for this section: publisher-page details, final-paper details, and gameplay execution details remain to be independently confirmed.

Direct links provided by candidate:

- DOI: [Candidate DOI link](https://doi.org/10.1109/COG64752.2025.11114278)
- Repository: [Candidate repository link](https://github.com/raatmarien/cheqqers)
- Live site: [Candidate live site link](https://cheqqers.com)

---

## 4. Ordinary checkers versus quantum checkers in very simple words

Ordinary checkers in very simple words:

- You have a board with dark and light squares.
- Each player has pieces that move diagonally.
- You capture by jumping over an opponent piece.
- Everything is certain. A square either has your piece, the opponent piece, or nothing. When it is your turn, you see the full board.

Quantum checkers in very simple words:

- It starts like checkers, but a piece can be uncertain.
- Uncertain means one piece can be spread over more than one square at the same time, with a chance to be found on each square if you look.
- You can make moves that create uncertainty or combine uncertain pieces back together.
- At some point the uncertainty must be resolved. Looking, capturing, or special rules can force the board to pick one definite outcome.
- Strategy changes because you must plan for chances, not just certain positions.

All detailed rule claims beyond this simple picture are **UNVERIFIED until the final paper is read**. Do not quote exact move legality, capture resolution, turn order, or win and draw rules from memory.

---

## 5. Superposition, measurement and collapse, occupancy and probabilities, split and merge and entangling moves, and levels - careful wording

This section uses careful wording only. Every specific rule detail requires full-paper verification.

- **Superposition:** General idea is that a piece is not on one definite square but is spread across squares with associated chances. **UNVERIFIED:** How the published game represents this, whether it uses true quantum amplitudes and phases or only classical probabilities, how many squares one piece can occupy, and what limits apply. Label all such details as requiring full-paper verification.
- **Measurement and collapse:** General idea is that an uncertain position becomes definite when measured. Think of it as looking at the board and the uncertainty snapping to one outcome. **UNVERIFIED:** What triggers measurement in the published rules, whether measurement is automatic or player-chosen, how randomness is sampled, and how captures interact with measurement. The voluntary measurement idea in our proposal is new only as a controlled optional move; whether the original game already has any voluntary measurement is **UNVERIFIED and must be checked against the full paper**.
- **Occupancy and probabilities:** General idea is that each square has a chance of containing a piece when measured. A display may show these chances as numbers or colors. **UNVERIFIED:** Exact meaning of occupancy in the paper, whether probabilities come from amplitudes, how phases affect them, and how the display is computed. Do not assume the display formula without reading the paper and inspecting the code logic directly.
- **Split, merge, and entangling moves:** General idea from prior review is that the game has moves that spread a piece, rejoin spread pieces, and create linked uncertainty between pieces. Careful wording: spread means one piece becomes uncertain across squares, rejoin means uncertain parts come back together, linked means the outcome of one piece affects another. **UNVERIFIED:** Exact move names, legality conditions, effects on game state, terminology used by the authors, and whether entanglement means full quantum entanglement or a game-specific linked rule. All of these require full-paper verification. Do not use the paper terms as if confirmed.
- **Levels:** Prior review suggested the game is introduced in stages or levels, possibly starting classical and adding quantum moves gradually. **UNVERIFIED:** How many levels exist, what each level allows, and what the authors call them. Mark any level description as requiring full-paper verification. Do not invent level numbers or names.
- **Phase and amplitude:** Prior review mentioned probability and phase displays. General idea is that quantum descriptions have both size of chance and an extra angle-like value that can affect how uncertainties combine. **UNVERIFIED:** Whether the published game actually uses phases in logic or only for display, and whether two-state or mixed-state descriptions are used. Requires full-paper and code verification.

Bottom line for this section: use only the simple ideas above when talking to others. For any precise claim, write **[REQUIRES FULL-PAPER VERIFICATION]** next to it until you have read the final paper.

---

## 6. What the published paper and repository already provide - not our contributions

Do not present any of the following as our contributions. Prior review suggests the published work already provides them, but each item below is **UNVERIFIED until we directly read the final paper, inspect the repository, and run the live site**.

- Existing rules for quantum checkers, including staged introduction and quantum moves - **UNVERIFIED in detail, do not quote exact rules**.
- A game engine that maintains game state and enforces moves - **UNVERIFIED in implementation detail and execution**.
- Agent baselines stated to include random play and a tree-search agent of the Monte Carlo Tree Search family - **UNVERIFIED in exact algorithm, settings, and strength**.
- Displays stated to show probabilities and possibly phases or amplitudes - **UNVERIFIED in exact computation and visual form**.
- Existing experiments and analysis reported in the paper - **UNVERIFIED: specific experiment identifiers, figure identifiers, metrics, and findings must not be cited until the final paper is read. Mark any such identifier as UNVERIFIED.**
- Live-site claims: a playable browser demo - **UNVERIFIED until independently opened and tested**.

Our job in reproduction is only to sanity-check a small part of this, not to rebuild it or claim it.

---

## 7. What is not novel if we merely reproduce it

Merely reproducing the following is not novel and must not be presented as a contribution:

- Re-implementing the existing rules or engine on its own.
- Re-running an existing paper experiment on its own.
- Adding a generic random player or generic tree-search player when the published work already describes such baselines.
- Adding a browser demo when a live site already exists.
- Adding a probability display when the published work already describes probability or phase displays.
- Using ordinary two-state or mixed-state descriptions if those are already part of the published approach. Whether they are, and in what form, is **UNVERIFIED**, so we must not claim novelty there without literature verification.
- Any polished presentation of the above without a new controlled comparison.

Novelty can only come from the controlled study described in Section 11, and even that is **CANDIDATE NOVELTY PENDING FULL-PAPER AND LITERATURE VERIFICATION**.

---

## 8. Proposed project title: a controlled study of voluntary measurement and probability-aware strategy

**Proposed project title:** A Controlled Study of Voluntary Measurement and Probability-Aware Strategy in Quantum Checkers

Short version for slides and file names: voluntary measurement study in quantum checkers.

This title is a proposal only. It must not be read as claiming that voluntary measurement is absent from the published game. Whether the published game already includes voluntary measurement is **UNVERIFIED and must be checked in the full paper**.

---

## 9. Research question

**Main research question:** When players or agents are given an explicit voluntary option to measure and resolve uncertainty, does probability-aware decision-making perform differently from classical-only or uncertainty-ignoring decision-making, and how does using measurement change game outcomes and game character?

Sub-questions for undergrad-level planning:

- Does a probability-aware search agent use quantum-like moves differently from a baseline that ignores probabilities?
- Does having the voluntary measurement option change collapse frequency, draw rate, and game length compared to a condition without it?
- Can a replay viewer that shows chances and phase or amplitude information help a beginner understand why a collapse happened?

All sub-questions depend on confirming that the voluntary measurement option as defined by us is not already the published rule. That check is **UNVERIFIED and pending full-paper and literature verification**.

---

## 10. Exact reproduction boundary, capped at about 25 to 30 percent of effort

Reproduction is deliberately small. Cap it at about 25 to 30 percent of total effort. Stop when the boundary is met. Do not expand it.

Include only:

1. **Rules and engine sanity checks:** Confirm the basic board setup, turn order, legal ordinary moves, and that quantum-like spread and rejoin behavior runs without crashing. Record any mismatch with the paper as a limitation. Do not re-derive or re-prove rules.
2. **One paper experiment reproduction:** Re-run exactly one experiment reported in the paper at small scale to check that the setup is understood. Do not invent or cite figure numbers, experiment numbers, metric values, or findings here. In all notes and code, refer to it as **[SPECIFIC FIGURE AND EXPERIMENT IDENTIFIER UNVERIFIED UNTIL FINAL PAPER IS READ]** and fill in the exact identifier only after reading.
3. **One baseline agent comparison:** Run one simple baseline comparison that the paper already describes, for example a random player versus a basic search player, just to confirm the harness can pit two agents against each other and log results. Prior review suggested random and tree-search baselines exist, but exact baseline definitions are **UNVERIFIED**. Use only what the paper defines after reading.

Explicitly out of scope for reproduction:

- No full re-implementation of all levels or all experiments.
- No tuning to beat reported results.
- No new display polish as part of reproduction.

Effort cap means if reproduction starts taking more than about one third of time, cut scope and move to kill-test decision in Section 16.

---

## 11. Proposed original contribution, 30 to 40 percent: voluntary Observe move, probability-aware search, controlled ablation, and replay viewer

**Status header, read first: ALL OF THIS SECTION IS CANDIDATE NOVELTY PENDING FULL-PAPER AND LITERATURE VERIFICATION. Do not present any item below as confirmed novel until the final paper has been read in full and follow-up and related literature has been searched.**

Proposed original work, kept to about 30 to 40 percent of effort:

- **Optional voluntary Observe measurement move:** Define one clear new action, called Observe, that a player or agent may choose on their turn instead of a board move. Choosing Observe selects an uncertain piece or region and forces its uncertainty to resolve to a definite outcome according to the same chance rule the engine already uses. State clearly in code and report whether Observe costs a turn, when it is legal, and what information is revealed. If the full paper already defines an equivalent voluntary measurement action, this contribution collapses and the project must switch to fallbacks in Section 18.
- **Probability-aware MCTS:** Extend a basic tree-search agent so that selection and rollout use occupancy chances rather than treating uncertain positions as definite. Keep the change small and documented so the difference from the baseline is testable. Do not claim generic tree search itself as new. Only the probability-aware modification under the voluntary-measurement condition is the candidate contribution, and only if verification shows it is not already in the paper.
- **Classical-only versus quantum-enabled controlled ablation:** Compare conditions where quantum-like moves and Observe are disabled versus enabled, with the same baseline strength otherwise. The point is to isolate the effect of the voluntary measurement option and probability-aware play. Keep board size, turn limits, and randomness handling identical across conditions except for the studied feature.
- **Sample size and intervals:** Aim for at least 170 games per condition if statistically justified for the comparison being made. Justify the number before running the full batch by checking variance in a small pilot, stating the comparison metric in advance, and confirming time budget from measured games per hour. Report Wilson intervals for win, draw, and collapse-related rates. Do not invent target win rates or expected outcomes in advance.
- **Metrics to log every game:** quantum-move usage, collapse frequency, draw rate, and game length, plus winner and reason for termination. Log enough state to recompute metrics without re-running games.
- **Phase and amplitude replay viewer:** Build a minimal viewer that can step through a logged game and show per-square chances and, only if confirmed in the paper and code, phase or amplitude information at each step with the collapse event marked. If phases are not actually used in the published logic, the viewer must say so plainly and show only chances. Do not claim a generic probability display or a browser demo as new.

Explicitly excluded from novelty claims:

- The browser demo itself is not new because a live site is already claimed.
- Generic tree search is not new.
- Probability or phase display in general is not new if already described.
- Ordinary two-state or mixed-state features are not new if already part of the published approach. Their exact status is **UNVERIFIED**.

---

## 12. Exact success metrics and deliverables

Success means all of the following are delivered and checkable, not just described:

- **Code:** Small, separate addition for the Observe action, probability-aware agent modification, and ablation switch, kept apart from reproduced logic so a reviewer can see the boundary. No invented file paths are listed here because repository structure is **UNVERIFIED**.
- **Tests:** Deterministic unit checks for move legality, measurement resolution handling, and log format, plus a fixed-seed smoke test that two agents can complete a game headlessly.
- **JSONL game logs:** One JSON object per line, one file per experimental condition, with fields for game identifier, random seed, condition label, move list, Observe usage, collapse events, termination reason, winner, and game length. Logs must be sufficient to regenerate plots and tables.
- **Plots:** At minimum, comparison of win and draw rates with Wilson intervals across conditions, collapse frequency comparison, game-length distribution comparison, and quantum-move usage comparison. Every plot must state sample size and condition definitions.
- **Demo:** Minimal playable or replayable demo that shows the Observe option and the replay viewer step-through. It does not need to be polished. It must state clearly what is reproduced versus what is new.
- **Reproducibility report:** Short report stating paper version read, code version inspected, environment pin, exact reproduction boundary from Section 10, full ablation definitions, sample sizes, time cost, and all mismatches found.
- **Limitations:** Explicit list of what was not verified, what was cut for time, collision risks found during literature search, and license constraints on reuse.

Pass threshold: reproduction boundary met, at least the planned games per condition completed or a justified smaller pilot with reasons recorded, Wilson intervals reported, logs and plots regenerable from seeds, and limitations honestly stated. Anything less is a partial result, not a pass.

---

## 13. Detailed five-person technical split with non-overlapping ownership, dependencies, and critical path

Every role owns code or measurement, not just writing. No role may be only writing or presentation. Each person writes their own methods and limitations section, and one person assembles, but assembly is extra, not the whole role.

- **Person A - Rules and engine guardian:** Owns the reproduction boundary for rules and engine sanity checks. Verifies turn order, ordinary move legality, and spread and rejoin behavior against the final paper. Produces deterministic legality tests and a mismatch log. Dependency: must deliver the legality test and mismatch log before others lock ablation definitions. No one else may change core rule logic.
- **Person B - Baseline agents and harness:** Owns the headless game runner, random baseline, and basic search baseline as defined by the paper after reading. Owns seed handling, games-per-hour measurement, and JSONL logging format. Dependency: needs Person A legality check to freeze move interface. Critical path: harness must run headlessly before any large batch.
- **Person C - Observe and probability-aware search:** Owns the voluntary Observe action definition and the probability-aware modification to search. Owns unit checks that Observe resolves uncertainty using the same chance rule as the engine. Dependency: needs Person A interface and Person B harness. Must keep new code in separate additions so the reproduction boundary stays visible. No one else may edit Observe logic.
- **Person D - Measurement, statistics, and plots:** Owns metric definitions, Wilson interval computation, sample-size justification including the at-least-170-games-per-condition check, and all plots from JSONL logs. Owns collapse frequency, draw rate, game length, and quantum-move usage analysis. Dependency: needs Person B log format and Person C condition labels. Must reject any plot that cannot be regenerated from logged seeds.
- **Person E - Replay viewer and reproducibility package:** Owns the minimal replay viewer with step-through and chance display, plus phase or amplitude display only if verified, and owns the pinned environment, demo assembly, reproducibility report skeleton, and limitations log. Dependency: needs Person B logs and Person C Observe definition. Also owns license check note and live-site comparison note.

Dependencies in order: A legality interface, then B harness and logging, then C Observe and agent change in parallel with E viewer skeleton, then D full statistics once pilot logs exist.

Critical path: A to B to pilot batch to D to final plots. If A or B slips, C and E work on isolated prototypes with mocked interfaces and re-integrate only after the interface freezes. Integration owner rotates weekly so no single person becomes a bottleneck.

---

## 14. Tools and setup: Python and TypeScript only if justified, Colab and laptop assumptions, pinned environment, no hardware requirement

- **Language choice:** Use Python or TypeScript only if justified by the existing repository. Do not introduce a new language unless the repository inspection shows it is needed. If the repository inspection shows a different setup, follow the repository and record the justification. Repository language and framework details are **UNVERIFIED** here and must be confirmed by direct inspection.
- **Colab and laptop assumptions:** Assume ordinary laptops and hosted notebooks are sufficient. Plan for headless runs in a notebook plus local runs for the viewer. Measure games per hour early in the kill test so batch sizes fit the timeline.
- **Pinned environment:** Pin the environment before the main batch. Record language version, package versions, random seeds, and repository version inspected. Keep the pin note inside the reproducibility report. No environment details are listed here because they were not independently checked while writing this file.
- **No hardware requirement:** No special quantum hardware, GPU cluster, or high-memory machine is required. If runs are slow, reduce board scope or game count with justification rather than requesting hardware. Engine slowdown risk is tracked in Section 17.
- **What not to do:** Do not add heavy dependencies, do not rewrite the engine in another language for convenience, and do not bypass license terms when copying code. See license risk in Section 17.

---

## 15. Background needed and one-week catch-up plan for beginners

Needed background, kept minimal:

- Basic checkers rules at the level of being able to play one casual game.
- Basic Python or TypeScript reading ability at the level of following a small game loop, depending on what repository inspection justifies.
- Basic probability at the level of understanding chance per square and average outcome over many games.
- Basic idea of tree search at the level of try moves, simulate, and pick the move with better average result. No deep quantum physics needed beyond the simple picture in Sections 4 and 5.

One-week catch-up plan:

- **Day 1 to 2 - Play and read:** Play one ordinary checkers game, read this brief, and read the final paper introduction and rules sections only. Write down every rule sentence that is unclear and mark it as needing verification.
- **Day 3 to 4 - Inspect and run:** Inspect the repository structure directly, open the live site directly, and run a tiny headless game if the kill test passes. Record what worked and what did not. Do not copy large amounts of code yet.
- **Day 5 - Probability and search:** Work through a tiny hand example of chances over squares and how a search agent could use those chances. Pair with Person B and Person C roles to see the harness interface.
- **Day 6 to 7 - Mini-prototype and verification:** Each person reproduces one tiny check, for example seed handling or log parsing, and the team jointly searches for follow-up work. End the week by listing all **UNVERIFIED** items that are now confirmed or still open.

---

## 16. 48-hour kill test with concrete pass and fail gates

Run this within the first 48 hours. Kill the project as a novel study if two or more gates fail. Record pass or fail for each gate in the reproducibility report.

- **Gate 1 - Confirm DOI and final publication:** Open the DOI link directly and confirm it leads to the correct publisher page for this exact paper title. Pass only if the publisher page loads and matches. Fail if the link does not resolve, shows a different paper, or shows only a preprint without final publication clarity. Status at brief-writing time: **UNVERIFIED**.
- **Gate 2 - Inspect paper-version code tag:** Inspect the repository directly for a tag, release, or commit note that marks the paper version. Pass only if a paper-version marker is found or the authors state which version matches the paper. Fail if no version can be tied to the paper. Repository contents are **UNVERIFIED**.
- **Gate 3 - Run a headless game in a notebook:** Run at least one full headless game between two simple agents using the existing code or a minimal harness. Pass only if a game completes without manual clicks and produces a log. Fail if no headless run is possible within the time box.
- **Gate 4 - Measure games per hour:** Time a small batch and compute achievable games per hour on available laptops or notebooks. Pass only if the rate supports the planned sample size within the multi-week timeline, or a justified reduced pilot is defined. Fail if the rate makes even a small pilot infeasible.
- **Gate 5 - Read full paper and search follow-up and tournament work:** Read the full final paper, not just the abstract, and search for follow-up papers, tournament reports, or related quantum-game work that already studies voluntary measurement or probability-aware search in this game. Pass only if no direct overlap is found after a documented search. Fail if equivalent voluntary measurement or equivalent probability-aware comparison already exists. Search terms and sources must be recorded.
- **Gate 6 - Implement a tiny Observe prototype:** Add a minimal voluntary measurement stub that is callable from the harness on a mocked or real state and resolves uncertainty using the engine chance rule. Pass only if the stub runs in at least one test game. Fail if Observe cannot be defined cleanly because measurement semantics in the paper are ambiguous or already cover it.

**Kill rule:** If two or more gates fail, stop the novel study. Switch to a fallback in Section 18. Do not negotiate the kill rule after the fact.

---

## 17. Adversarial risks

- **Existing work overlap:** The paper and repository already claim rules, engine, agents, displays, experiments, and a live site. Any uncited reuse looks like duplication. Mitigation: keep reproduction capped per Section 10 and mark all contribution claims as pending verification until Gate 5 passes.
- **Collision risk:** Others may extend the public demo or publish follow-ups while we work. Mitigation: document search date and sources in Gate 5, keep our addition narrow, and prefer a controlled comparison that is easy to distinguish.
- **Underpowered experiments:** Too few games produce noisy comparisons with wide intervals that prove nothing. Mitigation: require pilot variance check, pre-stated metric, at least 170 games per condition if justified, and Wilson intervals. If time does not allow it, report a pilot only and do not claim a finding.
- **Engine slowdown:** Quantum-like state tracking and search can be slow, breaking the batch plan. Mitigation: measure games per hour in Gate 4, cap search depth early, and define a reduced pilot in advance.
- **Ambiguous quantum semantics:** Terms like superposition, entanglement, phase, and mixed states may mean game-specific rules rather than textbook quantum behavior. Prior review mentions these ideas but exact semantics are **UNVERIFIED**. Mitigation: quote the paper definition after reading, implement exactly that, and state plainly where the game simplifies or departs from textbook quantum concepts.
- **AGPL license implications:** Prior review raised the possibility of a strong copyleft license, but the actual license file is **UNVERIFIED until directly read**. If a strong copyleft applies, copying, modifying, hosting, or distributing code can trigger source-sharing obligations. Mitigation: read the license file before copying, keep reproduced and new code separated, and record the license conclusion in the reproducibility package. Do not assume fair-use or classroom exemption.
- **Frontend and runtime uncertainty:** Live-site stack, build steps, and hosting behavior are **UNVERIFIED until the site and repository are directly inspected**. The demo may be hard to run locally. Mitigation: treat the viewer as minimal and separate, and do not promise a polished hosted demo until Gate 3 passes.
- **Moderate quantum depth:** The quantum content may be moderate rather than gate-model-heavy, more about chances and game rules than qubits and circuits. Do not oversell quantum depth. State the actual mechanism used after reading the paper, and frame the study as strategy under uncertainty rather than quantum computing.

---

## 18. Fallbacks: pure reproduction, probability-aware agent only, switch projects, and criteria for switching

- **Fallback A - Pure reproduction:** Drop the Observe idea and deliver a clean small reproduction with tests, logs, and limitations. Switch to this if Gate 6 fails because voluntary measurement is already present or cannot be defined cleanly, but Gates 1 to 4 pass.
- **Fallback B - Probability-aware agent only:** Drop the new Observe move and only compare a probability-aware agent against an uncertainty-ignoring baseline within existing rules. Switch to this if Observe overlaps published work but probability-aware comparison is still open after literature search.
- **Fallback C - Switch to the published QENM or surface-code teleportation project:** Abandon quantum checkers entirely and switch candidate projects. Switch to this if two or more kill-test gates fail, if Gate 5 finds direct overlap on both Observe and probability-aware play, or if license or runtime blocks make even reproduction infeasible.
- **Criteria for switching:** Use the kill rule in Section 16. Any switch must record which gates failed, what overlap was found with sources and dates, and what was preserved such as harness, logging, or statistics code. Do not drift into a new idea without writing down why the original failed.

---

## 19. Suggested multi-week timeline

This timeline assumes the kill test passes. If it does not, switch per Section 18 instead of stretching the timeline.

- **Week 1 - Verify and freeze:** Read the final paper in full, inspect repository version and license, open and test the live site, complete the 48-hour kill test, and freeze the reproduction boundary and ablation definitions. Deliverable: gate record with pass or fail per gate.
- **Week 2 - Reproduce small:** Complete rules and engine sanity checks, one paper experiment at small scale, and one baseline agent comparison with JSONL logging. Deliverable: reproduction logs plus mismatch list.
- **Week 3 - Build the new condition:** Implement Observe, probability-aware search modification, and minimal replay viewer step-through. Run a small pilot batch and check variance, games per hour, and Wilson interval widths. Deliverable: pilot plots with sample sizes stated.
- **Week 4 - Run the controlled batch:** Run the full at-least-170-games-per-condition batch if justified, or a justified pilot if not. Freeze logs and generate all comparison plots for quantum-move usage, collapse frequency, draw rate, and game length. Deliverable: frozen logs and plots.
- **Week 5 - Harden and report:** Add tests, clean the separation between reproduced and new code, finish the viewer, write the reproducibility report and limitations, and prepare the demo. Deliverable: code, tests, logs, plots, demo, and report as listed in Section 12.

Buffer rule: if any week slips by more than two days, cut viewer polish first, then cut full batch to justified pilot, never cut logging, intervals, or limitations.

---

## 20. References and direct links

Only the three candidate-provided links below are listed. Do not cite authors, venues, page numbers, figures, or follow-up works here because none were independently verified while writing this file. Add those only after Gate 1 and Gate 5 with full details and access dates.

- Candidate paper DOI link: [https://doi.org/10.1109/COG64752.2025.11114278](https://doi.org/10.1109/COG64752.2025.11114278) - **VERIFIED AS CANDIDATE-PROVIDED, resolution and publication details UNVERIFIED**
- Candidate repository link: [https://github.com/raatmarien/cheqqers](https://github.com/raatmarien/cheqqers) - **VERIFIED AS CANDIDATE-PROVIDED, contents and version UNVERIFIED**
- Candidate live site link: [https://cheqqers.com](https://cheqqers.com) - **VERIFIED AS CANDIDATE-PROVIDED, functionality UNVERIFIED**

Verification to add later:

- Publisher page confirmation record - **[TO BE ADDED AFTER GATE 1]**
- Final paper version read record - **[TO BE ADDED AFTER GATE 5]**
- Follow-up and tournament search record with sources and dates - **[TO BE ADDED AFTER GATE 5, MARKED UNVERIFIED UNTIL THEN]**
- Repository version and license read record - **[TO BE ADDED AFTER GATE 2]**

---

## 21. Frequently asked questions and decision answers

### What exactly are we building?

We are not building another ordinary checkers game and we are not claiming to invent quantum checkers. We are building a reproducible research study on top of the published Quantum Checkers engine:

1. Verify a small part of the published game and its baseline agent setup.
2. Add one explicitly defined voluntary measurement action, called `Observe`, only if the final paper does not already contain an equivalent action.
3. Add a probability-aware search modification.
4. Compare classical-only play with quantum-enabled play under controlled conditions.
5. Produce statistical results and a replay visualizer that shows what happened before and after measurement.

The research object is the **effect of voluntary measurement and probability-aware decision-making on gameplay**, not the existing game engine itself.

### Is this really quantum computing?

It uses quantum-inspired game mechanics and must be checked against the paper's actual state representation. The important distinction is whether the game uses genuine complex amplitudes and interference or a simplified probability game. That distinction is **UNVERIFIED until the final paper and code are inspected carefully**.

Do not describe the project as a full quantum computer, a hardware experiment, or a demonstration of quantum advantage. The safe description is:

> A quantum-combinatorial game study that investigates how superposition-like state uncertainty, measurement, and probability-aware search affect strategy.

If the paper's implementation turns out to use only classical probabilities without quantum amplitudes, say so explicitly. That would reduce the course-fit score and may trigger the fallback decision.

### Why is this better than our previous Decker/QCL project?

| Issue | Decker/QCL project | Quantum Checkers project |
|---|---|---|
| Collision risk | Another team selected the same paper | The paper is different, but class collision still needs instructor confirmation |
| Originality risk | The central idea was already close to existing work | Existing game is known, but a narrow controlled extension may be separable |
| Main activity | QML training, attack simulation, and security evaluation | Interactive quantum game, agent behavior, and controlled statistics |
| Demo quality | Mostly plots and attack metrics | Playable/replayable board with visible measurement and state changes |
| Technical risk | PennyLane/QKD/noise/security stack | Existing engine plus experiments, agent modification, and viewer |
| Main weakness | Novelty and paper collision | Moderate quantum depth and possible overlap with existing game AI work |
| Best defense | Security/noise experiment | Controlled ablation with pre-registered metrics and uncertainty intervals |

It is not automatically better in every academic dimension. It is better for **demo clarity, audience accessibility, and avoiding the exact Decker collision**. It is weaker if the course requires gate-model circuits or if the new measurement/agent experiment is already present in the literature.

### Why could we win with this project?

A course project does not need to invent a new quantum algorithm. It needs a clear reproduction, a defensible extension, and evidence.

We could perform well if we can show all of the following:

- The published paper and code were independently reproduced.
- The new action is clearly separated from existing rules.
- The agent comparison uses identical board sizes, seeds, time budgets, and baselines.
- The number of games is large enough for meaningful intervals.
- Results include null findings, not only favorable outcomes.
- The demo lets an examiner see the state, measurement, and strategy change immediately.
- Every claim is supported by logged games, scripts, and regenerated plots.

The strongest presentation sentence is:

> We did not merely create a quantum game; we measured how giving an agent control over measurement changes strategic behavior under a controlled experimental design.

That sentence is only defensible after the full-paper overlap search passes.

### What is the novelty in one sentence?

**Candidate novelty:** a controlled, reproducible comparison of voluntary measurement and probability-aware search against matched classical-only baselines in Quantum Checkers.

This is not confirmed novelty. It is a research hypothesis. It must be checked against:

- the final paper;
- the paper-version repository tag;
- tournament submissions;
- follow-up papers;
- related quantum-game projects;
- any thesis or public implementation studying the same ablation.

If an equivalent experiment already exists, remove it from the project title and use a different extension or switch projects.

### What parts are definitely not our novelty?

Do not claim originality for:

- the game concept itself;
- the existing rules;
- the existing engine;
- ordinary random or MCTS agents;
- the existing browser interface;
- a generic probability display;
- reproducing the paper's original win-rate table;
- simply adding more games or a larger board;
- simply porting the repository to another language.

### What would the live demo look like?

The audience sees a board and a replay timeline:

1. A piece has several possible locations.
2. The agent chooses either a normal move or `Observe`.
3. The state resolves to one outcome.
4. The viewer highlights the pre-measurement possibilities and the selected outcome.
5. A side panel shows the agent's choice, probability distribution, collapse event, and game statistics.
6. A second panel compares classical-only and quantum-enabled agents over many games.

The demo should be a replayable deterministic seed, not a claim that the audience is operating a quantum computer.

### What is the demo potential compared with the old project?

The demo potential is stronger than the Decker project for a non-specialist audience:

- Decker required explaining QCL training, eavesdropping, channel noise, and security metrics before the audience could interpret the result.
- Quantum Checkers can be understood immediately: make a move, measure a piece, watch the state resolve, then compare strategy.

The risk is that the demo can look like a game rather than research. The statistical experiment, uncertainty intervals, and controlled ablation are what make it a research demo rather than a software demo.

### How many people can genuinely work on it?

Five people can work on it if the interfaces are frozen early:

- Person A: rules and engine verification.
- Person B: baseline agents, game runner, and deterministic logging.
- Person C: `Observe` and probability-aware agent.
- Person D: experiment design, statistical tests, and plots.
- Person E: replay viewer, testing, and reproducibility package.

The critical path is A → B → C → D. E can build the viewer with mock JSONL data while the engine is being stabilized.

This is a real five-person split, but it is not five independent research papers. Persons A and B carry the reproduction foundation; Person C owns the main novelty; Person D owns evidence quality; Person E owns the demonstration and reproducibility layer.

### What if the `Observe` move is already in the paper?

Do not force it. Use one of these fallbacks:

- Study probability-aware versus uncertainty-ignoring search without adding a new rule.
- Study measurement timing under a new controlled condition not present in the paper.
- Study quantum-move usage and collapse statistics across levels with matched agents.
- Switch to the published QENM or surface-code teleportation project if both extensions are already covered.

The project is not allowed to claim novelty just because the code change is ours.

### What if the paper is published but the repository is broken?

A published paper does not guarantee usable code. We will:

1. Record the repository commit/tag and license.
2. Try the smallest headless example.
3. Separate repository failures from scientific failures.
4. Reimplement only the smallest reproduction boundary if the paper is clear.
5. Kill the project if the core semantics cannot be reconstructed reliably.

A broken repository is acceptable only if the paper provides a clear, manageable implementation route. A broken repository plus ambiguous rules is a kill condition.

### What is the collision risk?

The paper is specialized and appears to have a small repository footprint, but collision safety is not proven. The most obvious collision paths are:

- another team finding the same IEEE Conference on Games paper;
- students extending the existing MCTS agents;
- participants in Quantum Checkers tournaments making similar AI changes;
- the original authors publishing a follow-up during our project.

The team must register the exact paper and our proposed extension with the instructor before building. The registration message should state that our contribution is the voluntary-measurement/probability-aware ablation, not the game itself.

### Is the public code an advantage or a risk?

Both.

Advantages:

- faster initial reproduction;
- a concrete baseline;
- easier debugging;
- a path to a live demo;
- less risk of spending the whole project rebuilding infrastructure.

Risks:

- low originality if we only reuse it;
- dependency or version drift;
- paper/repository mismatch;
- unknown license obligations;
- hidden bugs;
- other teams can find the same repository;
- an existing agent or display may already implement our proposed idea.

Use the repository as a baseline and verification target, not as the project contribution.

### What would make us reject the project immediately?

Reject or switch if any two of these occur:

- DOI or final publication cannot be confirmed.
- The repository cannot run a headless game.
- The paper's state semantics cannot be understood well enough to define tests.
- The proposed `Observe` experiment already exists.
- Probability-aware search is already implemented or published in equivalent form.
- The game rate is too slow for a statistically meaningful experiment.
- The license prevents the planned reuse or redistribution.
- The course instructor says the topic is not quantum-computing appropriate.
- Another team has already registered the same paper or extension.

### What exactly do we submit at the end?

The final package should contain:

- a clean reproduction script;
- a separate implementation of the new condition;
- deterministic unit tests;
- JSONL game logs with seeds;
- win/draw/collapse/game-length plots;
- Wilson confidence intervals;
- the replay viewer;
- a paper-to-result comparison table;
- an originality and related-work table;
- a limitations section;
- a short live demo;
- a clean README explaining how to regenerate every result.

### What should we say if the result is negative?

A negative result is acceptable and may be more credible:

> Voluntary measurement did not improve win rate under our matched time budget, but it changed collapse frequency, game length, or draw behavior.

Do not optimize the agent until it produces a favorable result. Predefine the metrics and report the null result if that is what the experiment shows.

### How should we explain the project to the professor?

Use this short explanation:

> We will reproduce a small, well-defined part of a peer-reviewed quantum-combinatorial game paper. Our original work is a controlled ablation: we add or isolate voluntary measurement and probability-aware decision-making, then compare them against matched classical-only baselines using seeded games, confidence intervals, and a replay visualization. We are not claiming that the existing game engine or browser demo is novel.

### What is the final decision right now?

**Status: promising but not approved for full implementation.**

Quantum Checkers is attractive because of its demo and accessibility. It is not yet the safest research choice because publication details, code-version matching, exact quantum semantics, and extension novelty require the 48-hour gate.

Proceed only after Gates 1–6 are recorded. If it passes, freeze the scope exactly as written. If it fails two gates, switch rather than expanding the project to compensate.


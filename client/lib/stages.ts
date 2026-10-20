/**
 * Stage and mode catalogues, and the rule text the rules dialog shows.
 *
 * This is the single stage catalogue in the client. It used to be split across
 * `lib/stages.ts` and `components/game/stages.ts`, which held two copies of the
 * same five stages with different field names and different amounts of detail;
 * a copy that says "Stage 1 of 4" while this file says otherwise is exactly the
 * kind of drift that file was meant to prevent.
 *
 * Levels 0–3 follow the paper's classical, superposition, entanglement and
 * interference rules in the live paper engine. Level 4 adds custom decoherence.
 *
 * Numbering: levels are 0..4 on the wire. Everything a player reads is 1-based
 * ("Stage 2 of 5"), because the wire index is an implementation detail.
 */

export interface StageUnlock {
    title: string;
    body: string[];
    /** Credit line for a mechanic that is ours rather than the paper's. */
    credit?: string;
}

export interface StageDef {
    /** Wire level, 0..4. Never shown to the player on its own. */
    level: number;
    /** Short badge text, e.g. "SPLIT". */
    tag: string;
    /** Player-facing title, already 1-based. */
    title: string;
    /** One sentence: the mechanic this stage adds. */
    mechanic: string;
    /** The detail lines shown in the rules dialog. */
    detail: string[];
    /** Shown in the unlock dialog when the stage is reached for the first time. */
    unlock?: StageUnlock;
    /** Stages that are playable but never part of a batched experiment. */
    gameOnly?: string;
}

/** Stage numbers the server accepts (`server.rooms.SUPPORTED_LEVELS`). */
export const STAGES: StageDef[] = [
    {
        level: 0, tag: "CLASSICAL", title: "Stage 1 — Classical",
        mechanic: "English draughts: diagonal movement, forced captures and kings.",
        detail: [
            "White plays first. On an 8×8 board each side starts with 12 pieces across three rows; smaller boards use a scaled opening.",
            "Men step diagonally forward. A piece reaching the far edge becomes a king and can move in either direction.",
            "If a capture is available you must capture. Keep jumping with that same piece while another capture is available; crowning finishes the chain.",
            "You win when the opponent has no surviving pieces or no legal move. More than 40 completed turns without a capture is a draw.",
        ],
    },
    {
        level: 1, tag: "SPLIT", title: "Stage 2 — Superposition",
        mechanic: "Split one piece between two legal destinations, then move its branches.",
        detail: [
            "Choose Split on a piece and select two legal destination squares. Its source empties and each destination receives half that branch's probability.",
            "A branch can move normally or split again. All branches still belong to one original piece.",
            "Capturing measures a split attacker first. If it is not at the chosen starting square, the turn passes without measuring the defender.",
            "If the attacker is present, a split defender is measured next. The jump succeeds only if the defender is found on the jumped square; otherwise the turn passes.",
            "Forced captures, kings and the draw rule still apply. Voluntary Observe is an optional rule when creating a game; captures still measure automatically.",
        ],
    },
    {
        level: 2, tag: "ENTANGLEMENT", title: "Stage 3 — Entanglement",
        mechanic: "A certain piece capturing a split piece creates correlated outcomes.",
        detail: [
            "A certain attacker capturing a split defender does not immediately measure the defender. The board retains both the capture and no-move outcomes together.",
            "The attacker and defender are now correlated: learning one piece's position also restricts the other piece's possible outcome.",
            "Entangled branches can move and split. Other capture cases use the preceding stage's ordered measurements.",
            "The percentages are marginal chances. They cannot describe every correlation on their own.",
        ],
        unlock: {
            title: "Stage 3 unlocked — Entanglement",
            body: ["Captures on a split defender can now create correlated board states instead of measuring immediately.", "Move a branch by selecting its square, then choose a highlighted destination."],
            credit: "Based on section III.C of the Quantum Checkers paper.",
        },
    },
    {
        level: 3, tag: "INTERFERENCE", title: "Stage 4 — Interference",
        mechanic: "Recombine branches of the same original piece; their phases affect the result.",
        detail: [
            "Select one branch, choose Merge, then select another branch of that same original piece and a shared legal destination.",
            "Both source branches must have the same piece type and be able to move without capturing to the destination.",
            "Merge applies the inverse of the split operation. It combines complex amplitudes, so some probability can remain on the sources.",
            "Separate original pieces cannot merge. Equal percentages alone do not guarantee a complete merge: relative phase matters.",
        ],
        gameOnly: "Branch phases can reinforce or cancel when you merge them.",
    },
    {
        level: 4, tag: "DECOHERENCE", title: "Stage 5 — Decoherence",
        mechanic: "A custom extension: unresolved pieces lose coherence over time.",
        detail: [
            "This fifth stage is a project extension; the paper defines levels 0 through 3.",
            "An unresolved piece starts with six coherence ticks. Completed turns reduce its counter; at zero it is measured automatically.",
            "Observe is on by default at this stage. It lets you measure a selected piece voluntarily and consumes a turn. It cannot bypass a mandatory capture or a capture chain.",
            "Measurement projects the shared quantum state, so correlated pieces can change when one is measured. Split and merge refresh that piece's counter.",
        ],
        unlock: {
            title: "Stage 5 unlocked — Decoherence",
            body: ["Unresolved pieces now have a six-turn coherence clock.", "You can voluntarily Observe when no mandatory capture is available."],
            credit: "This clock and voluntary Observe are course-project extensions, not rules from the source paper.",
        },
        gameOnly: "Custom extension; no published experimental result is claimed for it.",
    },
];

export type StageMeta = StageDef;

/** How many stages there are. Distinct from `MAX_LEVEL`, which is the highest index. */
export const STAGE_COUNT = STAGES.length;

/** Highest stage unlocked by the progress record: completing N unlocks N+1. */
export const MAX_LEVEL = STAGES.length - 1;

/** Look up one stage's metadata; returns `undefined` for a number outside `0..4`. */
export function stageMeta(level: number): StageDef | undefined {
    return STAGES.find((stage) => stage.level === level);
}

/** Look up one stage's metadata, falling back to stage 0 for an unknown level. */
export function stageDef(level: number): StageDef {
    return STAGES.find((stage) => stage.level === level) ?? STAGES[0];
}

/** Player-facing stage number: the wire level plus one. */
export function stageNumber(level: number): number {
    return level + 1;
}

/** Playable modes (`server.rooms.MODES`), with what sits in each seat. */
export const MODES = [
    { value: "local", label: "Local 2 player", hint: "Two humans at this browser" },
    { value: "ai-easy", label: "vs AI — Easy", hint: "Seeded random agent" },
    { value: "ai-medium", label: "vs AI — Medium", hint: "UCT tree search · 200 simulations" },
    { value: "ai-hard", label: "vs AI — Hard", hint: "UCT tree search · 400 simulations" },
    { value: "online", label: "Online", hint: "Two browsers, join by lobby code" },
] as const;

export type ModeValue = (typeof MODES)[number]["value"];

/** `server.rooms.MODES` as a readonly array, for the type guard below. */
const MODE_VALUES: readonly string[] = MODES.map((mode) => mode.value);

export function isMode(value: string): value is ModeValue {
    return MODE_VALUES.includes(value);
}

export function modeLabel(value: string): string {
    return MODES.find((mode) => mode.value === value)?.label ?? value;
}

/**
 * The standing caveat shown wherever the board is: the model is
 * classical probability, so nothing here may imply amplitudes or a phase wheel.
 */
export const AMPLITUDE_CAVEAT =
    "The board shows measurement probabilities. Relative phase and correlations are retained in the live state and affect later moves.";

export const RULES_FOOTNOTE =
    "Levels 0–3 are based on Raat et al., Quantum Checkers (2025). Stage 5 is the project's custom decoherence extension.";

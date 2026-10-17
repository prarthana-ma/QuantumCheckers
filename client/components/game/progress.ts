/**
 * Local progress record, read from / written to `localStorage["qk.progress"]`.
 *
 * The shape matches the existing viewer (`viewer/game.js`): a map keyed by the
 * level as a string, each entry holding `{ games, wins }`. Completing a stage —
 * meaning finishing at least one game at that level — is what unlocks the next
 * one, and the unlock note for a stage is shown once per browser.
 *
 * Everything here is defensive: a private-mode browser or a hand-edited value
 * must degrade to "stage 0 only", never throw.
 */

export const PROGRESS_KEY = "qk.progress";

export interface StageProgress {
  games: number;
  wins: number;
}

export type ProgressRecord = Record<string, StageProgress>;

export function readProgress(): ProgressRecord {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(PROGRESS_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") return {};
    const out: ProgressRecord = {};
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (!/^\d+$/.test(key) || !value || typeof value !== "object") continue;
      const entry = value as Partial<StageProgress>;
      out[key] = {
        games: Number.isFinite(entry.games) ? Math.max(0, Number(entry.games)) : 0,
        wins: Number.isFinite(entry.wins) ? Math.max(0, Number(entry.wins)) : 0,
      };
    }
    return out;
  } catch {
    return {};
  }
}

export function writeProgress(progress: ProgressRecord): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(PROGRESS_KEY, JSON.stringify(progress));
  } catch {
    // Private mode or a full quota. The progress record is a convenience, so a
    // failed write is not worth interrupting play over.
  }
}

/** A stage counts as completed once at least one game has been played at it. */
export function isStageCompleted(progress: ProgressRecord, level: number): boolean {
  return (progress[String(level)]?.games ?? 0) > 0;
}

/** Highest stage reachable: 0 always, then one past the last completed stage. */
export function highestUnlockedLevel(progress: ProgressRecord, maxLevel: number): number {
  let level = 0;
  for (let candidate = 0; candidate < maxLevel; candidate += 1) {
    if (isStageCompleted(progress, candidate)) level = candidate + 1;
    else break;
  }
  return Math.min(level, maxLevel);
}

export function recordGame(
  progress: ProgressRecord,
  level: number,
  won: boolean,
): ProgressRecord {
  const key = String(level);
  const entry = progress[key] ?? { games: 0, wins: 0 };
  const next: ProgressRecord = {
    ...progress,
    [key]: {
      games: entry.games + 1,
      wins: entry.wins + (won ? 1 : 0),
    },
  };
  writeProgress(next);
  return next;
}

function unlockKey(level: number): string {
  return `${PROGRESS_KEY}.unlock.${level}`;
}

export function hasSeenUnlock(level: number): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(unlockKey(level)) === "1";
  } catch {
    return false;
  }
}

export function markUnlockSeen(level: number): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(unlockKey(level), "1");
  } catch {
    // Nothing to do — the note simply shows again next time.
  }
}
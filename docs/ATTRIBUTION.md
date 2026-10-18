# Attribution record

## Outer Space Loop (background soundtrack)

- **Author:** wipics.
- **Source:** [Outer Space Loop on OpenGameArt](https://opengameart.org/content/outer-space-loop).
- **Asset:** `client/public/audio/outer-space-loop.mp3`, downloaded unchanged from
  `https://opengameart.org/sites/default/files/outer_space_2.mp3` on 12 October 2026.
- **License:** [CC0 1.0 / public domain](https://creativecommons.org/publicdomain/zero/1.0/).
  The author's upload explicitly marks the track CC0 and Public Domain.
- The primary game's Music toggle controls this track independently of synthesized
  sound effects. Playback starts after a gesture, pauses in hidden tabs, and remembers
  the player's preference.

## Battle-CP (game shell design)

- **Source:** [github.com/Prajwal-k-tech/Battle-CP](https://github.com/Prajwal-k-tech/Battle-CP)
  by Prajwal K (live at [battle-cp.tech](https://battle-cp.tech/)).
- **What we took:** visual/UX design language only at first (dark ops-console theme,
  landing → lobby → rules → phased-play flow, HUD/status-strip patterns) — recreated
  in original CSS, zero of their files copied. Any exact elements lifted later are
  listed in this file with paths on both sides.
- **Basis:** the repository carries **no public license file** (verified October 2026),
  so reuse rests on the author's **direct written permission to our team lead**
  (DM, October 2026 — screenshot held by the team; produce on request).
- **Terms honored:** prominent credit here and in `README.md`; course/educational use;
  no claim of authorship over their design; if the author asks for removal or
  narrower scope, we comply and this file records the change.

### Name collisions checked (no code transplanted)

Our `client/hooks/useGameSocket.ts` shares a filename with the donor's
`frontend/hooks/useGameSocket.ts`. This is an independent implementation against
our own frozen `docs/PROTOCOL.md` — 184 lines against their 504, a different
message vocabulary, and no shared logic. The name was not chosen to mirror theirs.

One further check worth recording: the donor ships with **no public license file**.
That absence is the reason this whole arrangement rests on the author's written
permission rather than on a license grant. If that permission is ever withdrawn,
the position is unchanged — no donor code was ever copied, so nothing needs to be
torn out.

## Upstream Cheqqers (research anchor)

- **Source:** [github.com/raatmarien/cheqqers](https://github.com/raatmarien/cheqqers)
  (confirmed AGPL-3.0) — read-only reference. **Nothing copied**: no vendoring,
  wrapping, or re-implementation; see `qcheckers/engine/adapter.py` and
  `docs/REPRODUCIBILITY.md` §8.

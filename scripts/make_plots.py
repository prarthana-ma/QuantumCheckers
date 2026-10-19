"""CLI: read JSONL logs and write matplotlib PNGs into ``results/plots/``.

Owner: **Person D -- measurement, statistics and plots**.

Every figure this script produces states its sample size and the condition labels, as
brief section 12 requires, and every figure is regenerated purely from the logs -- no
plot may depend on state that is not in a log line. That is the rule Person D is
required to enforce (brief section 13), and this script is where it is enforced.

Plots produced
--------------
1. ``win_draw_rates.png`` -- win and draw rates per condition with Wilson intervals.
2. ``collapse_frequency.png`` -- fraction of games containing a collapse.
3. ``game_length.png`` -- game-length distribution per condition (box plot, plus
   individual points so a small sample is not over-claimed).
4. ``quantum_move_usage.png`` -- Observe and spread usage per game.
5. ``ablation_effects.png`` -- per-seed win-rate effect (obs minus noobs) for matched
   ablation condition pairs. The figure is always written; when no complete pair
   exists it states what is missing instead of silently omitting the figure.

Phase and amplitude are deliberately absent because this project's game engine stores
occupancy chances only. The independent Qiskit demonstration exercises phase in a
separate circuit; those circuit outputs are not game experiment measurements.

Usage
-----
::

    python scripts/make_plots.py
    python scripts/make_plots.py --results-dir results --out-dir results/plots
    python scripts/make_plots.py --log results/quantum-observe-vs-random.jsonl \\
        --log results/classical-mcts-vs-random.jsonl

Matplotlib is imported lazily inside :func:`main` so that ``--help`` works even before
the environment is installed, and so importing this module never forces a GUI
backend.
"""

from __future__ import annotations

import argparse
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qcheckers.experiment.config import CONDITIONS, MIN_GAMES_JUSTIFIED  # noqa: E402
from qcheckers.experiment.runner import read_jsonl  # noqa: E402
from qcheckers.experiment.stats import Rate, summarize  # noqa: E402

#: Figures written by :func:`main`, in order.
FIGURE_NAMES = (
    "win_draw_rates.png",
    "collapse_frequency.png",
    "game_length.png",
    "quantum_move_usage.png",
    "ablation_effects.png",
)

#: Shown on the ablation figure when no obs/noobs pair exists for the same base.
ABLATION_MISSING_MESSAGE = (
    "No ablation pairs found: needs obs and noobs logs for the same agent."
)

#: Footer text on every figure. Non-negotiable provenance, kept in one place.
PROVENANCE_FOOTER = (
    "QuriousMinds -- toy engine (upstream Cheqqers NOT integrated). "
    "Occurrence chances, not amplitudes. Toy-engine numbers are NOT paper results."
)


@dataclass(frozen=True, slots=True)
class LoadedLog:
    """One condition's log, its records and its summary.

    A small named record rather than a loose tuple, so a figure writer cannot silently
    swap a label for a summary.
    """

    label: str
    path: Path
    records: Sequence[Mapping[str, Any]]
    summary: dict[str, Any]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate plots from JSONL game logs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--results-dir",
        default="results",
        help="Directory to scan for *.jsonl logs.",
    )
    parser.add_argument(
        "--log",
        "--logs",
        dest="logs",
        action="append",
        default=None,
        help="Explicit log file. Repeatable. Overrides the directory scan.",
    )
    parser.add_argument(
        "--out-dir",
        "--out",
        default=None,
        help="Output directory (default: <results-dir>/plots).",
    )
    parser.add_argument(
        "--games",
        type=int,
        default=None,
        help="Cap games read per condition (oldest first). Use for a quick preview.",
    )
    parser.add_argument(
        "--dpi", type=int, default=150, help="Figure resolution."
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Only print one line per figure."
    )
    return parser.parse_args(argv)


def discover_logs(args: argparse.Namespace) -> list[Path]:
    """Return the log files to plot, in a stable order.

    Explicit ``--log`` paths win. Otherwise only the four registered baseline
    conditions and the two registered ablation arms are included. Server-play and
    browser-acceptance logs live in the same directory but are not experiment samples.
    Results are sorted by name so repeated runs produce identical figures.
    """
    if args.logs:
        return [Path(entry) for entry in args.logs]
    results_dir = Path(args.results_dir)
    if not results_dir.is_dir():
        return []
    report_labels = {condition.label for condition in CONDITIONS}
    report_labels.update(
        {"ablation-prob-vs-random-obs", "ablation-prob-vs-random-noobs"}
    )
    return sorted(
        path for path in results_dir.glob("*.jsonl") if path.stem in report_labels
    )


def load_summaries(paths: Sequence[Path], *, cap: int | None = None) -> list["LoadedLog"]:
    """Read each log and summarise it.

    Empty logs are skipped with a warning rather than plotted, because an empty axis
    reads as "zero result" when it actually means "no data".
    """
    loaded: list[LoadedLog] = []
    for path in paths:
        records = read_jsonl(path)
        if cap is not None:
            records = records[:cap]
        if not records:
            print(f"warning: {path} has no records; skipping", file=sys.stderr)
            continue
        label = str(records[0].get("condition") or path.stem)
        loaded.append(
            LoadedLog(
                label=label,
                path=path,
                records=records,
                summary=summarize(records),
            )
        )
    return loaded


def _footer(
    file_names: Sequence[str],
    argv: Sequence[str],
    condition_labels: Sequence[str],
    records_by_label: Mapping[str, Sequence[Mapping[str, Any]]],
) -> str:
    """Build the provenance footer using file names and labels only.

    Directory components are stripped from every path-looking argv token, so a
    footer embedded in a figure never leaks a local temporary or results path.
    """
    names = ", ".join(Path(name).name for name in file_names) or "(none)"

    safe_argv: list[str] = []
    for token in argv:
        candidate = Path(token)
        if candidate.is_absolute() or candidate.parent != Path("."):
            safe_argv.append(candidate.name)
        else:
            safe_argv.append(token)

    labels = ", ".join(str(label) for label in condition_labels) or "(none)"
    sample = (
        ", ".join(
            f"{label}: n={len(records_by_label.get(label, ()))}"
            for label in condition_labels
        )
        or "(none)"
    )
    return "\n".join(
        (
            PROVENANCE_FOOTER,
            f"source log(s): {names}",
            f"conditions: {labels}",
            f"sample size: {sample}",
            "command: " + shlex.join(["python", "scripts/make_plots.py", *safe_argv]),
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    command_args = list(argv) if argv is not None else sys.argv[1:]
    args = parse_args(argv)
    out_dir = Path(args.out_dir) if args.out_dir else Path(args.results_dir) / "plots"

    paths = discover_logs(args)
    if not paths:
        print(
            f"error: no JSONL logs found in {args.results_dir!r}. Run "
            "`python scripts/run_baseline.py` first.",
            file=sys.stderr,
        )
        return 2

    loaded = load_summaries(paths, cap=args.games)
    if not loaded:
        print("error: every log was empty; nothing to plot", file=sys.stderr)
        return 2

    try:
        import matplotlib

        matplotlib.use("Agg")  # headless: no display on CI or in a notebook re-run
        import matplotlib.pyplot as plt
    except ImportError as exc:
        print(
            f"error: matplotlib is required for plotting ({exc}). "
            "Install it with `pip install -r requirements.txt`.",
            file=sys.stderr,
        )
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    labels = [entry.label for entry in loaded]
    summaries = [entry.summary for entry in loaded]

    # Group by the condition recorded on each line, not just the first line of a
    # file: one JSONL log may legitimately contain several ablation arms.
    records_by_label: dict[str, list[Mapping[str, Any]]] = {}
    for entry in loaded:
        for record in entry.records:
            label = str(record.get("condition") or entry.label)
            records_by_label.setdefault(label, []).append(record)

    condition_labels = sorted(records_by_label) or labels
    footer = _footer(
        [entry.path.name for entry in loaded],
        command_args,
        condition_labels,
        records_by_label,
    )
    # PNG metadata carries the full paths as well; the visible footer is
    # deliberately filename-only so figures do not leak local directories.
    description = "\n".join(
        (
            footer,
            "full source path(s): "
            + ", ".join(str(entry.path) for entry in loaded),
            "command (as invoked): "
            + shlex.join(["python", "scripts/make_plots.py", *command_args]),
        )
    )

    if not args.quiet:
        print(f"engine        : {PROVENANCE_FOOTER}")
        print(f"logs          : {len(loaded)}")
        for entry in loaded:
            print(f"  {entry.path} -> {entry.label} (n={entry.summary['n_games']})")
        total = sum(s["n_games"] for s in summaries)
        print(f"games plotted : {total}")
        if any(s["n_games"] < MIN_GAMES_JUSTIFIED for s in summaries):
            print(
                f"WARNING       : at least one condition is below the brief's "
                f"{MIN_GAMES_JUSTIFIED}-per-condition target. Label these figures pilot."
            )
        print(f"output        : {out_dir}")
        print("")

    writers: tuple[tuple[str, Any], ...] = (
        ("win_draw_rates.png", plot_win_draw_rates),
        ("collapse_frequency.png", plot_collapse_frequency),
        ("game_length.png", plot_game_length),
        ("quantum_move_usage.png", plot_quantum_move_usage),
        ("ablation_effects.png", None),
    )

    written: list[Path] = []
    for filename, writer in writers:
        figure, axes = plt.subplots(figsize=(8.5, 5.0))
        try:
            if writer is None:
                # Two positional arguments: the ablation writer is also exercised
                # directly by tests.
                _plot_effects(axes, records_by_label)
            else:
                writer(axes, labels, summaries, loaded)
            figure.suptitle(
                f"{Path(filename).stem.replace('_', ' ')} -- QuriousMinds",
                fontsize=11,
            )
            figure.text(
                0.02,
                0.01,
                footer,
                ha="left",
                va="bottom",
                fontsize=6,
                color="#555555",
                wrap=True,
            )
            # Explicit margins rather than tight_layout: the rotated condition labels
            # and the per-figure caption below the axes make tight_layout unable to
            # find a valid solution and it silently warns instead of laying out.
            figure.subplots_adjust(left=0.11, right=0.98, top=0.88, bottom=0.38)
            target = out_dir / filename
            figure.savefig(
                target,
                dpi=args.dpi,
                metadata={"Description": description},
            )
            written.append(target)
            if args.quiet:
                print(f"wrote {target}")
        finally:
            plt.close(figure)

    if not args.quiet:
        print(f"figures       : {len(written)}")
        for path in written:
            print(f"  {path}")
    return 0


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def _sample_size_note(summaries: Sequence[Mapping[str, Any]]) -> str:
    """The "n = ..." annotation every figure carries."""
    return "  |  ".join(
        f"{label}: n={summary['n_games']}" for label, summary in zip(
            [str(s.get("condition")) for s in summaries], summaries
        )
    )


def _interval_bars(
    axes: Any,
    labels: Sequence[str],
    summaries: Sequence[Mapping[str, Any]],
    metric: str,
) -> tuple[list[float], list[float], list[float]]:
    """Point estimates plus Wilson interval bounds for one metric, per condition."""
    points: list[float] = []
    lows: list[float] = []
    highs: list[float] = []
    for summary in summaries:
        rate: Rate = summary["metrics"][metric]
        if not rate.defined:
            points.append(0.0)
            lows.append(0.0)
            highs.append(0.0)
            continue
        points.append(rate.point)
        lows.append(rate.low)
        highs.append(rate.high)
    return points, lows, highs


def plot_win_draw_rates(
    axes: Any,
    labels: Sequence[str],
    summaries: Sequence[Mapping[str, Any]],
    loaded: Sequence[LoadedLog],
) -> None:
    """Win rate for each player and the draw rate, with Wilson intervals.

    Brief section 12 asks for win and draw rates with Wilson intervals across
    conditions; this is that figure. Players are drawn side by side per condition so a
    second-player advantage is visible rather than hidden inside a single "win rate".
    """
    metrics = ("win_rate_p0", "win_rate_p1", "draw_rate")
    titles = ("player 0 wins", "player 1 wins", "draws")
    width = 0.26
    positions = list(range(len(labels)))

    for offset, (metric, title) in enumerate(zip(metrics, titles)):
        points, lows, highs = _interval_bars(axes, labels, summaries, metric)
        shifted = [position + (offset - 1) * width for position in positions]
        axes.bar(shifted, points, width=width * 0.9, label=title, zorder=2)
        axes.errorbar(
            shifted,
            points,
            yerr=[
                [max(0.0, p - lo) for p, lo in zip(points, lows)],
                [max(0.0, hi - p) for p, hi in zip(points, highs)],
            ],
            fmt="none",
            ecolor="#333333",
            elinewidth=1.0,
            capsize=3,
            zorder=3,
        )

    axes.set_xticks(positions)
    axes.set_xticklabels(labels, rotation=20, ha="right", fontsize=8)
    axes.set_ylabel("rate (0-1)")
    axes.set_ylim(0.0, 1.0)
    axes.set_title("Win and draw rates with 95% Wilson intervals")
    axes.grid(axis="y", alpha=0.3, zorder=0)
    axes.legend(fontsize=8, loc="upper right")
    axes.text(
        0.0,
        -0.34,
        f"n = {_sample_size_note(summaries)}",
        transform=axes.transAxes,
        fontsize=7,
        color="#555555",
    )


def plot_collapse_frequency(
    axes: Any,
    labels: Sequence[str],
    summaries: Sequence[Mapping[str, Any]],
    loaded: Sequence[LoadedLog],
) -> None:
    """Fraction of games containing at least one collapse, with Wilson intervals.

    Distinct from mean collapses per game: a rate answers "how often does measurement
    happen at all", which is the sub-question the brief actually asks.
    """
    points, lows, highs = _interval_bars(axes, labels, summaries, "collapse_rate")
    positions = list(range(len(labels)))
    axes.bar(positions, points, width=0.55, color="#4c72b0", zorder=2)
    axes.errorbar(
        positions,
        points,
        yerr=[
            [max(0.0, p - lo) for p, lo in zip(points, lows)],
            [max(0.0, hi - p) for p, hi in zip(points, highs)],
        ],
        fmt="none",
        ecolor="#333333",
        elinewidth=1.0,
        capsize=3,
        zorder=3,
    )
    for position, summary in zip(positions, summaries):
        axes.text(
            position,
            -0.09,
            f"{summary['rates']['mean_collapses']:.2f}/game",
            ha="center",
            va="top",
            fontsize=7,
            color="#555555",
        )

    axes.set_xticks(positions)
    axes.set_xticklabels(labels, rotation=20, ha="right", fontsize=8)
    axes.set_ylabel("fraction of games with >= 1 collapse")
    axes.set_ylim(0.0, 1.0)
    axes.set_title("Collapse frequency with 95% Wilson intervals")
    axes.grid(axis="y", alpha=0.3, zorder=0)
    axes.text(
        0.0,
        -0.34,
        f"n = {_sample_size_note(summaries)}  (label below bar = mean collapses per game)",
        transform=axes.transAxes,
        fontsize=7,
        color="#555555",
    )


def plot_game_length(
    axes: Any,
    labels: Sequence[str],
    summaries: Sequence[Mapping[str, Any]],
    loaded: Sequence[LoadedLog],
) -> None:
    """Game-length distribution per condition.

    Box plot plus jittered individual points. The points matter: a box plot of a
    dozen games implies a distribution the sample cannot support, and the brief warns
    against overpowered-looking claims from underpowered batches.
    """
    data = [
        [float(record.get("length", 0) or 0) for record in entry.records]
        for entry in loaded
    ]
    positions = list(range(len(labels)))
    axes.boxplot(data, positions=positions, widths=0.5, showfliers=False, zorder=2)

    for position, lengths in zip(positions, data):
        # Deterministic horizontal jitter: no RNG, so figures are byte-stable.
        for index, value in enumerate(lengths):
            spread = ((index % 7) - 3) / 40.0
            axes.plot(
                position + spread,
                value,
                marker=".",
                markersize=3,
                color="#333333",
                alpha=0.5,
                zorder=3,
            )

    means = [summary["rates"]["mean_length"] for summary in summaries]
    axes.plot(positions, means, marker="D", linestyle="none", color="#c44e52", zorder=4)
    for position, summary in zip(positions, summaries):
        axes.text(
            position,
            -0.09,
            f"mean {summary['rates']['mean_length']:.1f}\nsd {summary['rates']['stdev_length']:.1f}",
            ha="center",
            va="top",
            fontsize=7,
            color="#555555",
        )

    axes.set_xticks(positions)
    axes.set_xticklabels(labels, rotation=20, ha="right", fontsize=8)
    axes.set_ylabel("plies played")
    axes.set_title("Game-length distribution (box = IQR, dots = games, diamond = mean)")
    axes.grid(axis="y", alpha=0.3, zorder=0)
    axes.text(
        0.0,
        -0.34,
        f"n = {_sample_size_note(summaries)}",
        transform=axes.transAxes,
        fontsize=7,
        color="#555555",
    )


def plot_quantum_move_usage(
    axes: Any,
    labels: Sequence[str],
    summaries: Sequence[Mapping[str, Any]],
    loaded: Sequence[LoadedLog],
) -> None:
    """Grouped bars show Observe/spread moves per game on one axes.

    The caption also reports the fraction of games using each action at all. Both
    summaries matter, and they can disagree if a few games drive a high mean.
    """
    figure_width = 0.35
    positions = list(range(len(labels)))

    observe_means = [summary["rates"]["mean_observe_moves"] for summary in summaries]
    spread_means = [summary["rates"]["mean_spread_moves"] for summary in summaries]

    axes.bar(
        [p - figure_width / 2 for p in positions],
        observe_means,
        width=figure_width * 0.9,
        label="Observe moves / game",
        color="#55a868",
        zorder=2,
    )
    axes.bar(
        [p + figure_width / 2 for p in positions],
        spread_means,
        width=figure_width * 0.9,
        label="spread moves / game",
        color="#c44e52",
        zorder=2,
    )

    axes.set_xticks(positions)
    axes.set_xticklabels(labels, rotation=20, ha="right", fontsize=8)
    axes.set_ylabel("mean moves per game")
    axes.set_title("Quantum-move usage (Person C condition is Observe)")
    axes.grid(axis="y", alpha=0.3, zorder=0)
    axes.legend(fontsize=8, loc="upper right")
    axes.text(
        0.0,
        -0.34,
        f"n = {_sample_size_note(summaries)}  "
        "(games using each action at all: "
        + ", ".join(
            f"{label} observe {summary['metrics']['observe_usage'].point:.2f} "
            f"spread {summary['metrics']['spread_usage'].point:.2f}"
            for label, summary in zip(labels, summaries)
        )
        + ")",
        transform=axes.transAxes,
        fontsize=7,
        color="#555555",
    )


def _split_ablation_label(label: str) -> tuple[str, str] | None:
    """Return ``(base, arm)`` for an ``...-obs`` / ``...-noobs`` label."""
    if label.endswith("-noobs"):
        return label[: -len("-noobs")], "noobs"
    if label.endswith("-obs"):
        return label[: -len("-obs")], "obs"
    return None


def _expected_win_rate(
    records: Sequence[Mapping[str, Any]],
) -> dict[int, float]:
    """Expected win rate for player 0 per seed (a draw counts as half a win)."""
    scores: dict[int, list[float]] = {}
    for record in records:
        raw_seed: Any = record.get("seed")
        try:
            seed = int(raw_seed)
        except (TypeError, ValueError):
            seed = hash(str(raw_seed))
        raw_winner: Any = record.get("winner")
        try:
            winner: int | None = int(raw_winner)
        except (TypeError, ValueError):
            winner = None
        if winner == 0:
            score = 1.0
        elif winner == 1:
            score = 0.0
        else:
            # Draw (None winner) is half a win, not a loss.
            score = 0.5
        scores.setdefault(seed, []).append(score)
    return {seed: sum(values) / len(values) for seed, values in scores.items()}


def _plot_effects(
    axes: Any,
    records_by_label: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    """Plot per-seed win-rate effect (obs minus noobs) for matched ablations.

    When no complete obs/noobs pair exists the axes state that pair of logs is
    missing rather than raising or silently dropping the figure.
    """
    arms_by_base: dict[str, dict[str, str]] = {}
    for label in records_by_label:
        split = _split_ablation_label(str(label))
        if split is None:
            continue
        base, arm = split
        arms_by_base.setdefault(base, {})[arm] = str(label)

    pairs: list[tuple[str, dict[int, float]]] = []
    for base in sorted(arms_by_base):
        arms = arms_by_base[base]
        if "obs" not in arms or "noobs" not in arms:
            continue
        obs_scores = _expected_win_rate(records_by_label[arms["obs"]])
        noobs_scores = _expected_win_rate(records_by_label[arms["noobs"]])
        if not obs_scores or not noobs_scores:
            continue
        common = sorted(set(obs_scores) & set(noobs_scores))
        if common:
            effects = {
                seed: obs_scores[seed] - noobs_scores[seed] for seed in common
            }
        else:
            # No shared seeds: compare the arm means and label the seed as 0.
            obs_mean = sum(obs_scores.values()) / len(obs_scores)
            noobs_mean = sum(noobs_scores.values()) / len(noobs_scores)
            effects = {0: obs_mean - noobs_mean}
        pairs.append((base, effects))

    axes.set_title("Ablation effect: Observe minus no-Observe (per-seed win rate)")
    axes.axhline(0.0, color="#333333", linewidth=0.8, zorder=1)

    if not pairs:
        axes.text(
            0.5,
            0.5,
            ABLATION_MISSING_MESSAGE,
            transform=axes.transAxes,
            ha="center",
            va="center",
            fontsize=10,
            color="#555555",
        )
        axes.set_xticks([])
        axes.set_yticks([])
        return

    positions = list(range(len(pairs)))
    means = [sum(effects.values()) / len(effects) for _, effects in pairs]
    axes.bar(positions, means, width=0.55, color="#4c72b0", zorder=2)

    for position, (_, effects) in zip(positions, pairs):
        # Deterministic horizontal jitter: no RNG, so figures are byte-stable.
        for index, value in enumerate(effects.values()):
            spread = ((index % 7) - 3) / 40.0
            axes.plot(
                position + spread,
                value,
                marker="o",
                markersize=4,
                color="#c44e52",
                alpha=0.8,
                linestyle="none",
                zorder=3,
            )

    axes.set_xticks(positions)
    axes.set_xticklabels(
        [base.removeprefix("ablation-") for base, _ in pairs],
        rotation=20,
        ha="right",
        fontsize=8,
    )
    axes.set_ylabel("win-rate effect (obs - noobs)")
    axes.grid(axis="y", alpha=0.3, zorder=0)
    axes.text(
        0.0,
        -0.34,
        f"pairs = {len(pairs)}  |  seeds per pair = "
        + ", ".join(f"{base}: {len(effects)}" for base, effects in pairs),
        transform=axes.transAxes,
        fontsize=7,
        color="#555555",
    )


if __name__ == "__main__":
    raise SystemExit(main())

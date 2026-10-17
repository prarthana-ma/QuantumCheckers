"""Generate deterministic PNG summaries from experiment JSONL logs."""

from __future__ import annotations

import argparse
import glob
import json
import shlex
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qcheckers.experiment.config import (
    CONDITIONS,
    MIN_GAMES_JUSTIFIED,
    PRIMARY_METRIC,
)
from qcheckers.experiment.stats import (
    Rate,
    _observe_moves,
    _plies,
    _spread_moves,
    compare_conditions,
    summarize,
)

FIGURE_NAMES = (
    "win_draw_rates.png",
    "collapse_frequency.png",
    "game_length.png",
    "quantum_move_usage.png",
    "ablation_effects.png",
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate plots from experiment JSONL logs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--logs",
        nargs="+",
        default=["results/*.jsonl"],
        help="Experiment JSONL paths or glob patterns.",
    )
    parser.add_argument(
        "--out",
        default="results/plots",
        help="Directory for generated PNGs.",
    )
    return parser.parse_args(argv)


def _expand_logs(patterns: Sequence[str]) -> list[Path]:
    paths: set[Path] = set()
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            paths.update(Path(match) for match in matches)
        elif Path(pattern).is_file():
            paths.add(Path(pattern))
    return sorted(paths, key=lambda path: str(path))


def _read_experiment_logs(
    paths: Sequence[Path],
) -> tuple[dict[str, list[Mapping[str, Any]]], dict[str, list[str]]]:
    known_labels = {condition.label for condition in CONDITIONS}
    records_by_label: dict[str, list[Mapping[str, Any]]] = {}
    sources_by_label: dict[str, list[str]] = {}
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            print(f"warning: cannot read {path}: {exc}", file=sys.stderr)
            continue
        recognized = False
        for line_number, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                print(
                    f"warning: skipping invalid JSON in {path}:{line_number}: {exc}",
                    file=sys.stderr,
                )
                continue
            if not isinstance(record, dict):
                continue
            label = record.get("condition")
            if label not in known_labels:
                continue
            try:
                _plies(record)
                _observe_moves(record)
                _spread_moves(record)
                summarize([record])
            except (TypeError, ValueError) as exc:
                print(
                    f"warning: skipping invalid experiment record "
                    f"{path}:{line_number}: {exc}",
                    file=sys.stderr,
                )
                continue
            recognized = True
            records_by_label.setdefault(label, []).append(record)
            source_names = sources_by_label.setdefault(label, [])
            if path.name not in source_names:
                source_names.append(path.name)
        if not recognized:
            print(f"warning: {path} contains no recognized experiment records; skipping", file=sys.stderr)
    return records_by_label, sources_by_label


def _wilson_errors(rate: Rate) -> tuple[list[float], list[float]]:
    return [max(0.0, rate.p - rate.low)], [max(0.0, rate.high - rate.p)]


def _sample_note(
    labels: Sequence[str], records_by_label: Mapping[str, Sequence[Mapping[str, Any]]]
) -> str:
    return "  |  ".join(
        f"{label}: n={len(records_by_label[label])}" for label in labels
    )


def _footer(
    source_names: Sequence[str],
    command_args: Sequence[str],
    labels: Sequence[str],
    records_by_label: Mapping[str, Sequence[Mapping[str, Any]]],
) -> str:
    command = "python scripts/make_plots.py"
    if any(arg == "--logs" or arg.startswith("--logs=") for arg in command_args):
        command += " --logs " + " ".join(source_names)
    return (
        f"source: {', '.join(source_names)}\n"
        f"command: {command}\n"
        f"n: {_sample_note(labels, records_by_label)}"
    )


def _add_footer(
    figure: Any,
    source_names: Sequence[str],
    command_args: Sequence[str],
    labels: Sequence[str],
    records_by_label: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    figure.text(
        0.01,
        0.01,
        _footer(source_names, command_args, labels, records_by_label),
        ha="left",
        va="bottom",
        fontsize=7,
        color="#555555",
        wrap=True,
    )


def _png_metadata(command_args: Sequence[str], source_names: Sequence[str]) -> dict[str, str]:
    invocation = shlex.join(["python", "scripts/make_plots.py", *command_args])
    sources = ", ".join(source_names)
    return {
        "Description": f"command: {invocation}\nsource logs: {sources}",
        "Source": sources,
    }


def _plot_win_draw(axes: Any, labels: Sequence[str], summaries: Mapping[str, Any]) -> None:
    metrics = ("win_rate_p0", "win_rate_p1", "draw_rate")
    names = ("player 0 wins", "player 1 wins", "draws")
    positions = list(range(len(labels)))
    width = 0.25
    for index, (metric, name) in enumerate(zip(metrics, names)):
        rates: list[Rate] = [summaries[label]["metrics"][metric] for label in labels]
        points = [rate.p for rate in rates]
        errors = [
            [max(0.0, rate.p - rate.low) for rate in rates],
            [max(0.0, rate.high - rate.p) for rate in rates],
        ]
        offsets = [position + (index - 1) * width for position in positions]
        axes.bar(offsets, points, width=width * 0.9, label=name)
        axes.errorbar(offsets, points, yerr=errors, fmt="none", ecolor="#333333", capsize=3)
    axes.set_xticks(positions, labels, rotation=20, ha="right", fontsize=8)
    axes.set_ylim(0, 1)
    axes.set_ylabel("rate (0-1)")
    axes.set_title("Win and draw rates (95% Wilson intervals)")
    axes.legend(fontsize=8)
    axes.grid(axis="y", alpha=0.3)


def _plot_collapses(axes: Any, labels: Sequence[str], summaries: Mapping[str, Any]) -> None:
    positions = list(range(len(labels)))
    incidences = [summaries[label]["metrics"]["collapse_rate"] for label in labels]
    points = [value.p for value in incidences]
    errors = [
        [max(0.0, value.p - value.low) for value in incidences],
        [max(0.0, value.high - value.p) for value in incidences],
    ]
    axes.bar(positions, points, width=0.55, color="#4c72b0", label="games with collapse")
    axes.errorbar(positions, points, yerr=errors, fmt="none", ecolor="#333333", capsize=3)
    axes.set_ylabel("collapse incidence (0-1)")
    axes.set_ylim(0, 1)
    twin = axes.twinx()
    means = [summaries[label]["rates"]["mean_collapses"] for label in labels]
    twin.plot(positions, means, marker="D", color="#c44e52", label="mean collapses/game")
    twin.set_ylabel("mean collapses per game")
    axes.set_xticks(positions, labels, rotation=20, ha="right", fontsize=8)
    axes.set_title("Collapse incidence and mean collapses per game")
    axes.grid(axis="y", alpha=0.3)
    handles, names = axes.get_legend_handles_labels()
    other_handles, other_names = twin.get_legend_handles_labels()
    axes.legend(handles + other_handles, names + other_names, fontsize=8)


def _plot_lengths(
    axes: Any, labels: Sequence[str], records_by_label: Mapping[str, Sequence[Mapping[str, Any]]]
) -> None:
    values = [[_plies(record) for record in records_by_label[label]] for label in labels]
    positions = list(range(len(labels)))
    axes.boxplot(values, positions=positions, widths=0.5, showfliers=False)
    for position, lengths in zip(positions, values):
        for index, value in enumerate(lengths):
            jitter = ((index % 7) - 3) / 40.0
            axes.plot(position + jitter, value, ".", color="#333333", alpha=0.55)
        if lengths:
            mean = sum(lengths) / len(lengths)
            axes.plot(position, mean, marker="D", color="#c44e52")
    axes.set_xticks(positions, labels, rotation=20, ha="right", fontsize=8)
    axes.set_ylabel("plies played")
    axes.set_title("Game-length distribution (box, points, and mean)")
    axes.grid(axis="y", alpha=0.3)


def _plot_move_usage(
    axes: Any, labels: Sequence[str], records_by_label: Mapping[str, Sequence[Mapping[str, Any]]]
) -> None:
    positions = list(range(len(labels)))
    width = 0.36
    for offset, (accessor, name, color) in enumerate(
        ((_observe_moves, "Observe moves/game", "#55a868"),
         (_spread_moves, "Spread moves/game", "#c44e52"))
    ):
        means = [
            sum(accessor(record) for record in records_by_label[label])
            / len(records_by_label[label])
            for label in labels
        ]
        axes.bar(
            [position + (offset - 0.5) * width for position in positions],
            means,
            width=width * 0.9,
            label=name,
            color=color,
        )
    axes.set_xticks(positions, labels, rotation=20, ha="right", fontsize=8)
    axes.set_ylabel("mean moves per game")
    axes.set_title("Observe and spread move usage per game")
    axes.legend(fontsize=8)
    axes.grid(axis="y", alpha=0.3)


def _plot_effects(axes: Any, records_by_label: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
    contrasts = (
        ("mcts", "ablation-mcts-vs-random-obs", "ablation-mcts-vs-random-noobs"),
        ("prob", "ablation-prob-vs-random-obs", "ablation-prob-vs-random-noobs"),
    )
    available: list[tuple[str, Mapping[str, Any]]] = []
    for agent, observed_label, control_label in contrasts:
        observed = records_by_label.get(observed_label, [])
        control = records_by_label.get(control_label, [])
        if not observed or not control:
            continue
        result = compare_conditions(
            observed,
            control,
            metrics=(PRIMARY_METRIC,),
        )["comparisons"][PRIMARY_METRIC]
        available.append((agent, result))
    axes.set_ylim(-1, 1)
    axes.axhline(0, color="#555555", linewidth=1, linestyle="--")
    axes.set_ylabel(f"difference in {PRIMARY_METRIC} (Observe - no Observe)")
    axes.set_title("Ablation effect and comparison interval")
    axes.grid(axis="y", alpha=0.3)
    if not available:
        axes.text(
            0.5,
            0.75,
            "No ablation pairs found: needs obs and noobs logs for the same agent.",
            ha="center",
            va="center",
            transform=axes.transAxes,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 4},
        )
        axes.set_xticks([])
        return

    positions = list(range(len(available)))
    for position, (agent, result) in zip(positions, available):
        estimate = result["difference"]
        low = result["diff_low"]
        high = result["diff_high"]
        axes.errorbar(
            position,
            estimate,
            yerr=[[estimate - low], [high - estimate]],
            fmt="o",
            capsize=4,
        )
    axes.set_xticks(
        positions,
        [f"{agent}\n{result['method']}" for agent, result in available],
    )


def main(argv: Sequence[str] | None = None) -> int:
    command_args = list(argv) if argv is not None else sys.argv[1:]
    args = parse_args(argv)
    paths = _expand_logs(args.logs)
    if not paths:
        print("No experiment JSONL logs found; nothing to plot.", file=sys.stderr)
        return 0
    records_by_label, sources_by_label = _read_experiment_logs(paths)
    labels = sorted(records_by_label)
    if not labels:
        print("No experiment JSONL records found; nothing to plot.", file=sys.stderr)
        return 0

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib is required to generate plots.", file=sys.stderr)
        return 1

    summaries = {label: summarize(records_by_label[label]) for label in labels}
    pilot = any(len(records_by_label[label]) < MIN_GAMES_JUSTIFIED for label in labels)
    if pilot:
        low_conditions = [
            f"{label} (n={len(records_by_label[label])})"
            for label in labels
            if len(records_by_label[label]) < MIN_GAMES_JUSTIFIED
        ]
        print(
            f"warning: below MIN_GAMES_JUSTIFIED={MIN_GAMES_JUSTIFIED}: "
            + ", ".join(low_conditions),
            file=sys.stderr,
        )

    source_names = sorted({name for names in sources_by_label.values() for name in names})
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    writers = (
        ("win_draw_rates.png", _plot_win_draw),
        ("collapse_frequency.png", _plot_collapses),
        ("game_length.png", _plot_lengths),
        ("quantum_move_usage.png", _plot_move_usage),
    )
    for filename, writer in writers:
        figure, axes = plt.subplots(figsize=(9, 5.5))
        try:
            writer(axes, labels, summaries if writer in (_plot_win_draw, _plot_collapses) else records_by_label)
            title = filename.removesuffix(".png").replace("_", " ")
            figure.suptitle(f"{title}{' - PILOT' if pilot else ''}")
            _add_footer(figure, source_names, command_args, labels, records_by_label)
            figure.subplots_adjust(left=0.1, right=0.96, top=0.86, bottom=0.36)
            figure.savefig(
                out_dir / filename,
                dpi=140,
                metadata=_png_metadata(command_args, source_names),
            )
        finally:
            plt.close(figure)

    figure, axes = plt.subplots(figsize=(8, 5.5))
    try:
        _plot_effects(axes, records_by_label)
        figure.suptitle(f"ablation effects{' - PILOT' if pilot else ''}")
        _add_footer(figure, source_names, command_args, labels, records_by_label)
        figure.subplots_adjust(left=0.13, right=0.96, top=0.86, bottom=0.36)
        figure.savefig(
            out_dir / "ablation_effects.png",
            dpi=140,
            metadata=_png_metadata(command_args, source_names),
        )
    finally:
        plt.close(figure)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

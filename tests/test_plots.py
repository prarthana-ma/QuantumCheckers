"""Focused smoke test for experiment plot generation."""

import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("matplotlib")

from scripts import make_plots
from scripts.make_plots import FIGURE_NAMES, main


def _record(seed: int, label: str, winner: int | None) -> dict[str, Any]:
    return {
        "game_id": f"{label}-{seed}",
        "seed": seed,
        "condition": label,
        "winner": winner,
        "termination": "no_legal_moves",
        "length": 8 + seed,
        "collapses": seed % 2,
        "observe_moves": seed,
        "spread_moves": 2 - seed,
        "turns": [],
    }


def _write_log(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def test_main_writes_plots_from_old_shaped_jsonl(tmp_path: Path) -> None:
    log_path = tmp_path / "ablation-mcts-vs-random-obs.jsonl"
    _write_log(
        log_path,
        [
            _record(0, "ablation-mcts-vs-random-obs", 0),
            _record(1, "ablation-mcts-vs-random-noobs", 1),
            _record(2, "ablation-prob-vs-random-obs", None),
            _record(3, "ablation-prob-vs-random-noobs", 0),
        ],
    )
    output = tmp_path / "plots"

    assert main(["--logs", str(log_path), "--out", str(output)]) == 0
    for filename in FIGURE_NAMES:
        target = output / filename
        assert target.is_file()
        assert target.stat().st_size > 0
    from PIL import Image

    with Image.open(output / "ablation_effects.png") as image:
        assert str(log_path) in image.info["Description"]


def test_footer_contains_filename_without_directory(tmp_path: Path) -> None:
    log_path = tmp_path / "sample.jsonl"
    records_by_label = {"ablation-mcts-vs-random-obs": [_record(
        1, "ablation-mcts-vs-random-obs", 0
    )]}
    footer = make_plots._footer(
        [log_path.name],
        ["--logs", str(log_path), "--out", str(tmp_path / "plots")],
        list(records_by_label),
        records_by_label,
    )

    assert log_path.name in footer
    assert str(tmp_path) not in footer


def test_single_condition_ablation_plot_shows_missing_pairs_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_path = tmp_path / "single-condition.jsonl"
    _write_log(log_path, [_record(1, "ablation-mcts-vs-random-obs", 0)])
    output = tmp_path / "plots"
    passed_text: list[str] = []
    original_plot_effects = make_plots._plot_effects

    def capture_plot_text(axes: Any, records_by_label: Any) -> None:
        original_text = axes.text

        def capture_text(*args: Any, **kwargs: Any) -> Any:
            passed_text.append(str(args[2]))
            return original_text(*args, **kwargs)

        monkeypatch.setattr(axes, "text", capture_text)
        original_plot_effects(axes, records_by_label)

    monkeypatch.setattr(make_plots, "_plot_effects", capture_plot_text)
    assert main(["--logs", str(log_path), "--out", str(output)]) == 0
    assert (output / "ablation_effects.png").is_file()
    assert (
        "No ablation pairs found: needs obs and noobs logs for the same agent."
        in passed_text
    )


def test_matched_ablation_conditions_write_effect_plot(tmp_path: Path) -> None:
    log_path = tmp_path / "matched-ablation.jsonl"
    _write_log(
        log_path,
        [
            _record(1, "ablation-mcts-vs-random-obs", 0),
            _record(1, "ablation-mcts-vs-random-noobs", 1),
        ],
    )
    output = tmp_path / "plots"

    assert main(["--logs", str(log_path), "--out", str(output)]) == 0
    target = output / "ablation_effects.png"
    assert target.is_file()
    assert target.stat().st_size > 0

"""Seed management for reproducible experiments.

Derives independent, reproducible seeds for individual games and stochastic
components from a single root seed. All derivations are deterministic: the same
root seed and parts always produce the same derived seed.

Derivation formula: polynomial hash over (root, *parts) modulo 2**31.
"""

from __future__ import annotations

import hashlib
from typing import Sequence


def derive_seed(root: int, *parts: int) -> int:
    """Derive a non-negative seed from ``root`` and ``parts``.

    Uses SHA-256 of the concatenated integer string, mod 2**31. Deterministic:
    the same inputs always produce the same output.
    """
    if root < 0:
        raise ValueError(f"root seed must be >= 0, got {root}")
    payload = "|".join([str(root), *(str(p) for p in parts)])
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % (2**31)


class SeedManager:
    """Manages seed derivation for an experiment run.

    A single root seed produces independent seeds for each game, each agent within
    a game, and each replay export. Recording all seeds allows full reproduction.
    """

    def __init__(self, root_seed: int) -> None:
        if root_seed < 0:
            raise ValueError(f"root_seed must be >= 0, got {root_seed}")
        self.root_seed = int(root_seed)

    def game_seed(self, game_index: int) -> int:
        """Seed for the engine of game ``game_index``."""
        return derive_seed(self.root_seed, 0, game_index)

    def agent_seed(self, game_index: int, agent_slot: int) -> int:
        """Seed for agent ``agent_slot`` (0 or 1) in game ``game_index``."""
        if agent_slot not in (0, 1):
            raise ValueError(f"agent_slot must be 0 or 1, got {agent_slot}")
        return derive_seed(self.root_seed, 1, game_index, agent_slot)

    def replay_seed(self, game_index: int) -> int:
        """Seed for replay export of game ``game_index``."""
        return derive_seed(self.root_seed, 2, game_index)

    def derive(self, *parts: int) -> int:
        """General derivation from root seed and integer parts."""
        return derive_seed(self.root_seed, *parts)

    def manifest(self) -> dict[str, object]:
        """Return a dict describing the seed policy for recording in results."""
        return {
            "root_seed": self.root_seed,
            "derivation": "sha256(root|part1|part2|...) mod 2**31",
            "formula": "derive_seed(root, *parts) -> sha256(root|p1|p2|...)[:4] % 2**31",
        }

    def game_seeds(self, n_games: int) -> list[int]:
        """Return the list of engine seeds for ``n_games`` games."""
        return [self.game_seed(i) for i in range(n_games)]


__all__ = ["SeedManager", "derive_seed"]

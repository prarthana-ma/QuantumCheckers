"""Tests for seed management."""

from __future__ import annotations

import pytest

from qcheckers.experiment.seeds import SeedManager, derive_seed


class TestDeriveSeed:
    def test_deterministic(self):
        assert derive_seed(42, 0, 1) == derive_seed(42, 0, 1)

    def test_different_parts_differ(self):
        assert derive_seed(42, 0, 1) != derive_seed(42, 0, 2)

    def test_different_roots_differ(self):
        assert derive_seed(0, 0, 1) != derive_seed(1, 0, 1)

    def test_non_negative(self):
        for root in range(10):
            for part in range(5):
                assert derive_seed(root, part) >= 0

    def test_within_int32(self):
        s = derive_seed(2**30, 100, 200)
        assert 0 <= s < 2**31

    def test_negative_root_raises(self):
        with pytest.raises(ValueError):
            derive_seed(-1, 0)


class TestSeedManager:
    def test_game_seed_deterministic(self):
        mgr = SeedManager(100)
        assert mgr.game_seed(0) == mgr.game_seed(0)
        assert mgr.game_seed(0) != mgr.game_seed(1)

    def test_agent_seed(self):
        mgr = SeedManager(100)
        assert mgr.agent_seed(0, 0) != mgr.agent_seed(0, 1)
        assert mgr.agent_seed(0, 0) == mgr.agent_seed(0, 0)

    def test_replay_seed(self):
        mgr = SeedManager(100)
        assert mgr.replay_seed(0) != mgr.replay_seed(1)

    def test_manifest(self):
        mgr = SeedManager(55)
        m = mgr.manifest()
        assert m["root_seed"] == 55
        assert "derivation" in m

    def test_game_seeds_list(self):
        mgr = SeedManager(10)
        seeds = mgr.game_seeds(5)
        assert len(seeds) == 5
        assert len(set(seeds)) == 5  # all distinct

    def test_negative_root_raises(self):
        with pytest.raises(ValueError):
            SeedManager(-5)

    def test_derive_general(self):
        mgr = SeedManager(200)
        assert mgr.derive(1, 2, 3) == mgr.derive(1, 2, 3)
        assert mgr.derive(1, 2, 3) != mgr.derive(1, 2, 4)

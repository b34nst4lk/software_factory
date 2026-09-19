"""Tests for config.py — defaults and override overlay."""

from __future__ import annotations

import pytest

import config


def test_default_config_has_expected_models_and_cycle_cap():
    c = config.default("/repo", "software-factory", ".scratch/software-factory/impl/*.md")
    assert c.implementer_model == "deepseek-v4-flash:cloud"
    assert c.inner_verifier_model == "deepseek-v4-pro:cloud"
    assert c.final_verifier_model == "glm-5.3-flash:cloud"
    assert c.implementer_effort == "low"
    assert c.final_verifier_effort == "low"
    assert c.cycle_cap == 5
    assert config.FAILOVER_RETRIES == 3
    assert config.FAILOVER_BACKOFF_S == (5, 15, 45)


def test_default_config_no_longer_exposes_single_verifier_model():
    # maps to: B3 — the legacy single verifier_model field is gone (replaced by inner/final).
    c = config.default("/repo", "e", "g")
    assert not hasattr(c, "verifier_model")


def test_with_overlays_applies_cli_flags_ignoring_none():
    c = config.default("/repo", "e", "g")
    c2 = c.with_overrides(cycle_cap=3, mock=True, pr_stage=None, no_approve=None)
    assert c2.cycle_cap == 3
    assert c2.mock is True
    assert c2.pr_stage is True  # unchanged (None ignored)


def test_impl_and_issues_dirs_derive_from_effort():
    c = config.default("/repo", "software-factory", "g")
    assert c.impl_dir.endswith(".scratch/software-factory/impl")
    assert c.issues_dir.endswith(".scratch/software-factory/issues")


def test_default_db_path_resolves_to_factory_state_db():
    # maps to: config.db_path defaults to <repo>/.factory/state.db so live runs log.
    c = config.default("/repo", "software-factory", "g")
    assert c.db_path == "/repo/.factory/state.db"


def test_config_without_db_path_is_an_invalid_state():
    # maps to: make invalid states impossible — a Config with no db_path asserts.
    with pytest.raises(AssertionError):
        config.Config(repo_path="/repo", effort="e", impl_glob="g")

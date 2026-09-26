"""Opt-in capability for synthetic cases only."""

import pytest


@pytest.fixture
def enable_fixture_policy(monkeypatch):
    monkeypatch.setenv("ORGANON_ALLOW_FIXTURES", "1")

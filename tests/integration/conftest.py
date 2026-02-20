"""
Integration test configuration.
Registers the 'integration' pytest marker.
"""
import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: marks tests requiring a running docker compose stack",
    )

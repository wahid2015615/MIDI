"""Auto-mark pytest items: unit | integration | security."""

from __future__ import annotations

import pytest

_INTEGRATION = {
    "test_http_api.py",
    "test_ui_payload_wiring.py",
    "test_ui_to_midi.py",
}
_SECURITY = {
    "test_security.py",
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        name = item.path.name if hasattr(item, "path") else item.fspath.basename
        if name in _SECURITY:
            item.add_marker(pytest.mark.security)
        elif name in _INTEGRATION:
            item.add_marker(pytest.mark.integration)
        else:
            item.add_marker(pytest.mark.unit)

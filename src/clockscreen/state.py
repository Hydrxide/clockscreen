"""clockscreen-state.json: what the app remembers between runs (the geocoding result).

One key per entry. Writes go to a temporary file that replaces the old one, so a stop
mid-write never leaves a half-written file.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class State:
    def __init__(self, path: Path | None) -> None:
        self.path = path  # None = remember nothing (tests)
        self._data: dict[str, Any] = {}
        if path is not None and path.exists():
            try:
                self._data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                log.warning("Ignoring unreadable %s: %s", path, exc)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        if self.path is None:
            return
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

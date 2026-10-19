"""The README's copy-paste HController entry still matches the code."""

import re
from pathlib import Path

import yaml

from clockscreen.config import Config

ROOT = Path(__file__).resolve().parents[1]


def module_block() -> str:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    match = re.search(r"<!-- hcontroller-module.*?-->\s*```yaml\n(.*?)```", readme, re.S)
    assert match, "README lost its hcontroller-module block"
    return match.group(1)


def test_readme_module_entry():
    # Indented two spaces, so it pastes straight under an existing `modules:` key.
    modules = yaml.safe_load("modules:\n" + module_block())["modules"]
    assert list(modules) == ["clockscreen"]
    entry = modules["clockscreen"]
    assert entry["url"] == f"http://127.0.0.1:{Config().server.port}"
    assert entry["command"] == [".venv/bin/python", "-m", "clockscreen"]
    assert entry["cwd"] == "~/clockscreen"
    assert entry["health"] == "/health" and entry["ui"] == "/"
    assert entry["display"] == {"frame": "/render/frame"}
    assert entry["config_file"] == "config.yaml"
    assert (ROOT / entry["config_example"]).exists()

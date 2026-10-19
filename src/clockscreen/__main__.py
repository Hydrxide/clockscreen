"""Entry point: ``python -m clockscreen [--config config.yaml]``."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import uvicorn

from .api.app import create_app
from .config import load_config
from .runtime import Runtime


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="clockscreen", description="Clock and local weather for a 128x64 LED panel")
    parser.add_argument("--config", "-c", help="YAML config file (default: ./config.yaml if present)")
    parser.add_argument("--host", help="override server.host")
    parser.add_argument("--port", type=int, help="override server.port")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    # httpx logs every request at INFO; the weather calls are summarised by the poller instead.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    config_path = args.config or ("config.yaml" if Path("config.yaml").exists() else None)
    config = load_config(config_path)

    # The geocoding result is remembered next to the config, so restarts don't look it up again.
    state_dir = Path(config_path).resolve().parent if config_path else Path.cwd()
    runtime = Runtime(config, state_path=state_dir / "clockscreen-state.json")
    uvicorn.run(
        create_app(runtime),
        host=args.host or config.server.host,
        port=args.port or config.server.port,
        log_level=args.log_level.lower(),
        # HController fetches a frame up to 60 times a second; don't log each one.
        access_log=False,
    )


if __name__ == "__main__":
    main()

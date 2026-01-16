from __future__ import annotations

from .config import load_config
from .watcher import run_watcher


def main() -> None:
    config = load_config()
    run_watcher(config)


if __name__ == "__main__":
    main()

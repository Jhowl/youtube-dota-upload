from __future__ import annotations

import threading

import uvicorn

from .config import load_config
from .store import init_db
from .watcher import run_watcher
from .web_app import create_app


def main() -> None:
    config = load_config()
    init_db(config.uploads_db_path)

    app = create_app(config)
    watcher_thread = threading.Thread(target=run_watcher, args=(config,), daemon=True)
    watcher_thread.start()

    uvicorn.run(app, host="0.0.0.0", port=config.web_port, log_level="info", access_log=False)


if __name__ == "__main__":
    main()

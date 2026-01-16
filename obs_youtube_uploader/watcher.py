from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import queue
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers.polling import PollingObserver

from .config import Config
from .process_video import process_video


def _is_wanted(file_path: Path, exts: set[str]) -> bool:
    return file_path.suffix.lower() in exts


def _wait_for_stable(file_path: Path, *, stable_seconds: int = 20, poll_interval: float = 2.0) -> None:
    last_size = -1
    stable_for = 0.0

    while True:
        try:
            size = file_path.stat().st_size
        except FileNotFoundError:
            time.sleep(poll_interval)
            continue

        if size == last_size and size > 0:
            stable_for += poll_interval
            if stable_for >= stable_seconds:
                return
        else:
            stable_for = 0.0
            last_size = size

        time.sleep(poll_interval)


@dataclass
class _WorkItem:
    path: Path


class _Handler(FileSystemEventHandler):
    def __init__(self, config: Config, work_q: queue.Queue[_WorkItem]):
        super().__init__()
        self._config = config
        self._q = work_q

    def on_created(self, event):
        if event.is_directory:
            return
        p = Path(event.src_path)
        if not _is_wanted(p, self._config.video_extensions):
            return
        self._q.put(_WorkItem(path=p))


def run_watcher(config: Config) -> None:
    config.watch_folder.mkdir(parents=True, exist_ok=True)

    work_q: queue.Queue[_WorkItem] = queue.Queue()

    observer = PollingObserver(timeout=2)
    observer.schedule(_Handler(config, work_q), str(config.watch_folder), recursive=False)
    observer.start()

    print(f"[watcher] watching: {config.watch_folder}")

    try:
        if config.process_existing:
            for entry in sorted(config.watch_folder.iterdir()):
                if entry.is_file() and _is_wanted(entry, config.video_extensions):
                    work_q.put(_WorkItem(path=entry))

        while True:
            item = work_q.get()

            # Wait for OBS to finish writing.
            _wait_for_stable(item.path, stable_seconds=20, poll_interval=2.0)

            process_video(config, item.path)

    except KeyboardInterrupt:
        print("[watcher] stopping...")
    finally:
        observer.stop()
        observer.join(timeout=10)

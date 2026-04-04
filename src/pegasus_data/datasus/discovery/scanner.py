from __future__ import annotations

import ftplib
import json
import queue
import re
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath, Path

from ...common.storage import ensure_parent
from ...config import get_settings


_LIST_UNIX = re.compile(
    r"^(?P<mode>[bcdlps-][rwx-]{9})\s+\d+\s+\S+\s+\S+\s+"
    r"(?P<size>\d+)\s+(?P<month>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})\s+"
    r"(?P<timeyear>[\d:]{4,5})\s+(?P<name>.+)$"
)


@dataclass(frozen=True)
class ScanEntry:
    parent_directory: str
    child_name: str
    full_path: str
    entry_type: str | None
    size: int | None
    modified: str | None
    listing_method: str
    scan_timestamp: float
    worker_id: int
    error_flags: list[str]


class DatasusFtpScanner:
    def __init__(self, *, host: str | None = None, base_path: str | None = None, connections: int | None = None) -> None:
        settings = get_settings()
        self.host = host or settings.datasus_ftp_host
        self.base_path = base_path or settings.datasus_ftp_base_path
        self.connections = connections or settings.datasus_scan_connections
        self.timeout = settings.datasus_scan_timeout_seconds

    def _connect(self) -> ftplib.FTP:
        ftp = ftplib.FTP(self.host, timeout=self.timeout)
        ftp.login()
        ftp.set_pasv(True)
        return ftp

    def _mlsd_entries(self, ftp: ftplib.FTP, directory: str) -> list[ScanEntry]:
        rows: list[ScanEntry] = []
        for name, facts in ftp.mlsd(directory):
            full_path = str(PurePosixPath(directory) / name)
            rows.append(
                ScanEntry(
                    parent_directory=directory,
                    child_name=name,
                    full_path=full_path,
                    entry_type=facts.get("type"),
                    size=int(facts["size"]) if facts.get("size", "").isdigit() else None,
                    modified=facts.get("modify"),
                    listing_method="MLSD",
                    scan_timestamp=time.time(),
                    worker_id=-1,
                    error_flags=[],
                )
            )
        return rows

    def _list_entries(self, ftp: ftplib.FTP, directory: str) -> list[ScanEntry]:
        raw_lines: list[str] = []
        ftp.retrlines(f"LIST {directory}", raw_lines.append)
        rows: list[ScanEntry] = []
        for line in raw_lines:
            match = _LIST_UNIX.match(line)
            if not match:
                continue
            name = match.group("name")
            full_path = str(PurePosixPath(directory) / name)
            mode = match.group("mode")
            entry_type = "dir" if mode.startswith("d") else "file"
            rows.append(
                ScanEntry(
                    parent_directory=directory,
                    child_name=name,
                    full_path=full_path,
                    entry_type=entry_type,
                    size=int(match.group("size")),
                    modified=None,
                    listing_method="LIST",
                    scan_timestamp=time.time(),
                    worker_id=-1,
                    error_flags=[],
                )
            )
        return rows

    def _nlst_entries(self, ftp: ftplib.FTP, directory: str) -> list[ScanEntry]:
        rows: list[ScanEntry] = []
        for child in ftp.nlst(directory):
            pure = PurePosixPath(child)
            rows.append(
                ScanEntry(
                    parent_directory=str(pure.parent),
                    child_name=pure.name,
                    full_path=str(pure),
                    entry_type=None,
                    size=None,
                    modified=None,
                    listing_method="NLST",
                    scan_timestamp=time.time(),
                    worker_id=-1,
                    error_flags=[],
                )
            )
        return rows

    def _list_directory(self, ftp: ftplib.FTP, directory: str) -> list[ScanEntry]:
        try:
            return self._mlsd_entries(ftp, directory)
        except Exception:
            pass
        try:
            return self._list_entries(ftp, directory)
        except Exception:
            return self._nlst_entries(ftp, directory)

    def scan_to_jsonl(self, *, output_path: str, checkpoint_path: str | None = None) -> None:
        queue_dirs: queue.Queue[str] = queue.Queue()
        queue_dirs.put(self.base_path)
        visited: set[str] = set()
        visited_lock = threading.Lock()
        output_lock = threading.Lock()
        stop_token = object()
        checkpoint = Path(checkpoint_path) if checkpoint_path else None
        output = ensure_parent(output_path)

        def persist_checkpoint() -> None:
            if checkpoint is None:
                return
            ensure_parent(checkpoint)
            with checkpoint.open("w", encoding="utf-8") as handle:
                json.dump({"visited": sorted(visited), "pending": list(queue_dirs.queue)}, handle, ensure_ascii=False, indent=2)

        def worker(worker_id: int) -> None:
            ftp = self._connect()
            try:
                while True:
                    directory = queue_dirs.get()
                    if directory is stop_token:
                        return
                    with visited_lock:
                        if directory in visited:
                            queue_dirs.task_done()
                            continue
                        visited.add(directory)
                    try:
                        rows = self._list_directory(ftp, directory)
                    except Exception:
                        queue_dirs.task_done()
                        continue
                    for row in rows:
                        row = ScanEntry(**{**asdict(row), "worker_id": worker_id})
                        with output_lock:
                            with output.open("a", encoding="utf-8") as handle:
                                handle.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
                        if row.entry_type == "dir":
                            queue_dirs.put(row.full_path)
                    queue_dirs.task_done()
                    if checkpoint is not None and len(visited) % 250 == 0:
                        persist_checkpoint()
            finally:
                try:
                    ftp.quit()
                except Exception:
                    ftp.close()

        threads = [threading.Thread(target=worker, args=(idx,), daemon=True) for idx in range(self.connections)]
        for thread in threads:
            thread.start()
        queue_dirs.join()
        for _ in threads:
            queue_dirs.put(stop_token)
        for thread in threads:
            thread.join()
        persist_checkpoint()

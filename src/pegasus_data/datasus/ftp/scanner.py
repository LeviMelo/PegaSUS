from __future__ import annotations

import ftplib
import json
import queue
import re
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from ...common.storage import ensure_parent
from ...config import get_settings
from .state import ScanState

_LIST_UNIX = re.compile(
    r'^(?P<mode>[bcdlps-][rwx-]{9})\s+\d+\s+\S+\s+\S+\s+'
    r'(?P<size>\d+)\s+(?P<month>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})\s+'
    r'(?P<timeyear>[\d:]{4,5})\s+(?P<name>.+)$'
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

    def to_dict(self) -> dict:
        return asdict(self)


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
        rows = []
        for name, facts in ftp.mlsd(directory):
            entry_type = facts.get('type')
            if entry_type in {'cdir', 'pdir'}:
                continue
            rows.append(ScanEntry(
                parent_directory=directory,
                child_name=name,
                full_path=str(PurePosixPath(directory) / name),
                entry_type=entry_type,
                size=int(facts['size']) if facts.get('size', '').isdigit() else None,
                modified=facts.get('modify'),
                listing_method='MLSD',
                scan_timestamp=time.time(),
                worker_id=-1,
                error_flags=[],
            ))
        return rows

    def _list_entries(self, ftp: ftplib.FTP, directory: str) -> list[ScanEntry]:
        raw_lines: list[str] = []
        ftp.retrlines(f'LIST {directory}', raw_lines.append)
        rows: list[ScanEntry] = []
        for line in raw_lines:
            match = _LIST_UNIX.match(line)
            if not match:
                continue
            name = match.group('name')
            rows.append(ScanEntry(
                parent_directory=directory,
                child_name=name,
                full_path=str(PurePosixPath(directory) / name),
                entry_type='dir' if match.group('mode').startswith('d') else 'file',
                size=int(match.group('size')),
                modified=None,
                listing_method='LIST',
                scan_timestamp=time.time(),
                worker_id=-1,
                error_flags=[],
            ))
        return rows

    def _nlst_entries(self, ftp: ftplib.FTP, directory: str) -> list[ScanEntry]:
        rows = []
        for child in ftp.nlst(directory):
            pure = PurePosixPath(child)
            rows.append(ScanEntry(
                parent_directory=str(pure.parent),
                child_name=pure.name,
                full_path=str(pure),
                entry_type=None,
                size=None,
                modified=None,
                listing_method='NLST',
                scan_timestamp=time.time(),
                worker_id=-1,
                error_flags=['unknown_entry_type'],
            ))
        return rows

    def _list_directory(self, ftp: ftplib.FTP, directory: str) -> list[ScanEntry]:
        for method in (self._mlsd_entries, self._list_entries, self._nlst_entries):
            try:
                return method(ftp, directory)
            except Exception:
                continue
        raise RuntimeError(f'Could not list directory: {directory}')

    def scan_to_jsonl(self, *, output_path: str, checkpoint_path: str | None = None, append: bool = True) -> ScanState:
        stop_token = object()
        out = ensure_parent(output_path)
        checkpoint = Path(checkpoint_path) if checkpoint_path else None
        state = ScanState.from_file(checkpoint) if checkpoint and checkpoint.exists() else ScanState(
            pending_dirs=[self.base_path],
        )
        pending: queue.Queue[object] = queue.Queue()
        for item in state.pending_dirs or [self.base_path]:
            pending.put(item)
        visited_lock = threading.Lock()
        output_lock = threading.Lock()
        state_lock = threading.Lock()
        started_fresh = not append
        if started_fresh and out.exists():
            out.unlink()

        def flush_state() -> None:
            if checkpoint is None:
                return
            with state_lock:
                snapshot = ScanState(
                    visited_dirs=set(state.visited_dirs),
                    pending_dirs=[item for item in list(pending.queue) if isinstance(item, str)],
                    errors=list(state.errors),
                    entries_written=state.entries_written,
                )
            snapshot.save(checkpoint)

        def worker(worker_id: int) -> None:
            ftp = self._connect()
            try:
                while True:
                    directory = pending.get()
                    if directory is stop_token:
                        pending.task_done()
                        return
                    assert isinstance(directory, str)
                    with visited_lock:
                        if directory in state.visited_dirs:
                            pending.task_done()
                            continue
                        state.visited_dirs.add(directory)
                    try:
                        rows = self._list_directory(ftp, directory)
                    except Exception as exc:
                        with state_lock:
                            state.errors.append({'directory': directory, 'worker_id': worker_id, 'error': str(exc)})
                        pending.task_done()
                        continue
                    local_lines = []
                    for row in rows:
                        enriched = ScanEntry(**{**row.to_dict(), 'worker_id': worker_id})
                        local_lines.append(json.dumps(enriched.to_dict(), ensure_ascii=False))
                        if enriched.entry_type == 'dir':
                            pending.put(enriched.full_path)
                    with output_lock:
                        with out.open('a', encoding='utf-8') as handle:
                            for line in local_lines:
                                handle.write(line + '\n')
                    with state_lock:
                        state.entries_written += len(local_lines)
                    pending.task_done()
                    if checkpoint and state.entries_written % 1000 == 0:
                        flush_state()
            finally:
                try:
                    ftp.quit()
                except Exception:
                    ftp.close()

        threads = [threading.Thread(target=worker, args=(idx,), daemon=True) for idx in range(self.connections)]
        for thread in threads:
            thread.start()
        pending.join()
        for _ in threads:
            pending.put(stop_token)
        for thread in threads:
            thread.join()
        flush_state()
        return state

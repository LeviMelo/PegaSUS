from __future__ import annotations

import ftplib
import json
import queue
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from ...common.logging import get_logger
from ...common.storage import ensure_parent
from ...config import get_settings
from .state import ScanState

_LIST_UNIX = re.compile(
    r'^(?P<mode>[bcdlps-][rwx-]{9})\s+\d+\s+\S+\s+\S+\s+'
    r'(?P<size>\d+)\s+(?P<month>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})\s+'
    r'(?P<timeyear>[\d:]{4,5})\s+(?P<name>.+)$'
)
_FILE_SUFFIX_HINTS = (
    '.dbc', '.dbf', '.zip', '.gz', '.csv', '.json', '.xml',
    '.pdf', '.txt', '.xls', '.xlsx', '.doc', '.docx',
)
_LOG = get_logger(__name__)


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
        self.base_path = self._normalize_path(base_path or settings.datasus_ftp_base_path)
        self.connections = connections or settings.datasus_scan_connections
        self.timeout = settings.datasus_scan_timeout_seconds

    def _connect(self) -> ftplib.FTP:
        ftp = ftplib.FTP(self.host, timeout=self.timeout)
        ftp.login()
        ftp.set_pasv(True)
        return ftp

    def _normalize_path(self, path: str) -> str:
        pure = PurePosixPath(path or '/')
        normalized = str(pure)
        return normalized if normalized.startswith('/') else f'/{normalized}'

    def _directory_variants(self, directory: str) -> list[str]:
        return [self._normalize_path(directory)]

    def _join_child(self, directory: str, child: str) -> str:
        if child.startswith('/'):
            return self._normalize_path(child)
        return self._normalize_path(str(PurePosixPath(self._normalize_path(directory)) / child))

    @contextmanager
    def _cwd(self, ftp: ftplib.FTP, directory: str):
        original = ftp.pwd()
        ftp.cwd(directory)
        try:
            yield
        finally:
            ftp.cwd(original)

    def _mlsd_entries(self, ftp: ftplib.FTP, directory: str) -> list[ScanEntry]:
        errors: list[str] = []
        for candidate in self._directory_variants(directory):
            for mode in ('direct', 'cwd'):
                try:
                    if mode == 'direct':
                        listing = ftp.mlsd(candidate)
                    else:
                        with self._cwd(ftp, candidate):
                            listing = ftp.mlsd()

                    rows: list[ScanEntry] = []
                    for name, facts in listing:
                        entry_type = facts.get('type')
                        if entry_type in {'cdir', 'pdir'}:
                            continue
                        rows.append(ScanEntry(
                            parent_directory=self._normalize_path(directory),
                            child_name=name,
                            full_path=self._join_child(directory, name),
                            entry_type=entry_type,
                            size=int(facts['size']) if facts.get('size', '').isdigit() else None,
                            modified=facts.get('modify'),
                            listing_method=f'MLSD:{mode}',
                            scan_timestamp=time.time(),
                            worker_id=-1,
                            error_flags=[],
                        ))
                    return rows
                except Exception as exc:
                    errors.append(f'{candidate}/{mode}: {exc}')
        raise RuntimeError('MLSD failed: ' + '; '.join(errors))

    def _list_entries(self, ftp: ftplib.FTP, directory: str) -> list[ScanEntry]:
        errors: list[str] = []
        for candidate in self._directory_variants(directory):
            for command, mode in ((f'LIST {candidate}', 'direct'), ('LIST', 'cwd')):
                raw_lines: list[str] = []
                try:
                    if mode == 'cwd':
                        with self._cwd(ftp, candidate):
                            ftp.retrlines(command, raw_lines.append)
                    else:
                        ftp.retrlines(command, raw_lines.append)

                    if not raw_lines:
                        return []

                    rows: list[ScanEntry] = []
                    parsed_any = False
                    for line in raw_lines:
                        match = _LIST_UNIX.match(line)
                        if not match:
                            continue
                        parsed_any = True
                        name = match.group('name')
                        rows.append(ScanEntry(
                            parent_directory=self._normalize_path(directory),
                            child_name=name,
                            full_path=self._join_child(directory, name),
                            entry_type='dir' if match.group('mode').startswith('d') else 'file',
                            size=int(match.group('size')),
                            modified=None,
                            listing_method=f'LIST:{mode}',
                            scan_timestamp=time.time(),
                            worker_id=-1,
                            error_flags=[],
                        ))
                    if parsed_any:
                        return rows
                    errors.append(f'{candidate}/{mode}: unparseable LIST rows')
                except Exception as exc:
                    errors.append(f'{candidate}/{mode}: {exc}')
        raise RuntimeError('LIST failed: ' + '; '.join(errors))

    def _infer_entry_type_hint(self, child_name: str) -> str | None:
        name = PurePosixPath(child_name).name.lower()
        if not name or name in {'.', '..'}:
            return None
        if any(name.endswith(suffix) for suffix in _FILE_SUFFIX_HINTS):
            return 'file'
        return None

    def _probe_entry_type(self, ftp: ftplib.FTP, full_path: str, *, child_name: str | None = None) -> str | None:
        hinted = self._infer_entry_type_hint(child_name or PurePosixPath(full_path).name)
        if hinted is not None:
            return hinted

        original = ftp.pwd()
        try:
            ftp.cwd(full_path)
            return 'dir'
        except Exception:
            return 'file'
        finally:
            try:
                ftp.cwd(original)
            except Exception:
                pass

    def _nlst_entries(self, ftp: ftplib.FTP, directory: str) -> list[ScanEntry]:
        errors: list[str] = []
        for candidate in self._directory_variants(directory):
            for mode in ('direct', 'cwd'):
                try:
                    if mode == 'direct':
                        children = ftp.nlst(candidate)
                    else:
                        with self._cwd(ftp, candidate):
                            children = ftp.nlst()

                    rows: list[ScanEntry] = []
                    for child in children:
                        name = PurePosixPath(child).name if '/' in child else child
                        if name in {'.', '..'}:
                            continue
                        full_path = self._join_child(directory, child)
                        rows.append(ScanEntry(
                            parent_directory=self._normalize_path(directory),
                            child_name=name,
                            full_path=full_path,
                            entry_type=self._probe_entry_type(ftp, full_path, child_name=name),
                            size=None,
                            modified=None,
                            listing_method=f'NLST:{mode}',
                            scan_timestamp=time.time(),
                            worker_id=-1,
                            error_flags=['entry_type_probed'],
                        ))
                    return rows
                except Exception as exc:
                    errors.append(f'{candidate}/{mode}: {exc}')
        raise RuntimeError('NLST failed: ' + '; '.join(errors))

    def _list_directory(self, ftp: ftplib.FTP, directory: str) -> list[ScanEntry]:
        errors: list[str] = []
        for method in (self._mlsd_entries, self._list_entries, self._nlst_entries):
            try:
                return method(ftp, directory)
            except Exception as exc:
                errors.append(f'{method.__name__}: {exc}')
        raise RuntimeError(f'Could not list directory: {directory} ({"; ".join(errors)})')

    def _load_or_initialize_state(self, checkpoint: Path | None) -> ScanState:
        if checkpoint and checkpoint.exists():
            state = ScanState.from_file(checkpoint)
            if not state.pending_dirs and not state.in_progress_dirs and state.entries_written == 0:
                _LOG.warning(
                    'checkpoint %s has zero entries and no pending/in-progress directories; restarting scan from %s',
                    checkpoint,
                    self.base_path,
                )
                return ScanState(pending_dirs=[self.base_path])
            return state
        return ScanState(pending_dirs=[self.base_path])

    def scan_to_jsonl(self, *, output_path: str, checkpoint_path: str | None = None, append: bool = True) -> ScanState:
        stop_token = object()
        out = ensure_parent(output_path)
        checkpoint = Path(checkpoint_path) if checkpoint_path else None

        if append:
            state = self._load_or_initialize_state(checkpoint)
        else:
            state = ScanState(pending_dirs=[self.base_path])
            if out.exists():
                out.unlink()
            if checkpoint and checkpoint.exists():
                checkpoint.unlink()

        pending: queue.Queue[object] = queue.Queue()
        seed_dirs: list[str] = []
        seen_seed: set[str] = set()
        for item in list(state.pending_dirs) + sorted(state.in_progress_dirs):
            normalized = self._normalize_path(str(item))
            if normalized not in seen_seed:
                seen_seed.add(normalized)
                seed_dirs.append(normalized)
        if not seed_dirs:
            seed_dirs = [self.base_path]
        for item in seed_dirs:
            pending.put(item)

        output_lock = threading.Lock()
        state_lock = threading.Lock()
        checkpoint_lock = threading.Lock()
        last_checkpoint_entries = state.entries_written

        def flush_state() -> None:
            if checkpoint is None:
                return
            with state_lock:
                snapshot = ScanState(
                    completed_dirs=set(state.completed_dirs),
                    in_progress_dirs=set(state.in_progress_dirs),
                    pending_dirs=[item for item in list(pending.queue) if isinstance(item, str)],
                    errors=list(state.errors),
                    entries_written=state.entries_written,
                )
            snapshot.save(checkpoint)

        def maybe_flush_state() -> None:
            nonlocal last_checkpoint_entries
            if checkpoint is None:
                return
            with checkpoint_lock:
                current_entries = state.entries_written
                if current_entries - last_checkpoint_entries < 1000:
                    return
                last_checkpoint_entries = current_entries
            flush_state()

        def worker(worker_id: int) -> None:
            ftp = self._connect()
            try:
                while True:
                    directory = pending.get()
                    if directory is stop_token:
                        pending.task_done()
                        return
                    assert isinstance(directory, str)

                    with state_lock:
                        if directory in state.completed_dirs or directory in state.in_progress_dirs:
                            pending.task_done()
                            continue
                        state.in_progress_dirs.add(directory)

                    try:
                        rows = self._list_directory(ftp, directory)
                    except Exception as exc:
                        _LOG.warning('scan listing failed for %s: %s', directory, exc)
                        with state_lock:
                            state.in_progress_dirs.discard(directory)
                            state.errors.append({
                                'directory': directory,
                                'worker_id': worker_id,
                                'error': str(exc),
                            })
                        pending.task_done()
                        maybe_flush_state()
                        continue

                    local_lines: list[str] = []
                    discovered_dirs: list[str] = []
                    for row in rows:
                        enriched = ScanEntry(**{**row.to_dict(), 'worker_id': worker_id})
                        local_lines.append(json.dumps(enriched.to_dict(), ensure_ascii=False))
                        if enriched.entry_type == 'dir':
                            discovered_dirs.append(self._normalize_path(enriched.full_path))

                    with output_lock:
                        with out.open('a', encoding='utf-8') as handle:
                            for line in local_lines:
                                handle.write(line + '\n')

                    with state_lock:
                        for child_dir in discovered_dirs:
                            if child_dir not in state.completed_dirs and child_dir not in state.in_progress_dirs:
                                pending.put(child_dir)
                        state.entries_written += len(local_lines)
                        state.in_progress_dirs.discard(directory)
                        state.completed_dirs.add(directory)

                    pending.task_done()
                    maybe_flush_state()
            finally:
                try:
                    ftp.quit()
                except Exception:
                    ftp.close()

        threads = [threading.Thread(target=worker, args=(idx,), daemon=True) for idx in range(self.connections)]
        for thread in threads:
            thread.start()

        interrupted = False
        try:
            pending.join()
        except KeyboardInterrupt:
            interrupted = True
            _LOG.warning('scan interrupted by user; saving checkpoint')
            flush_state()
            raise
        finally:
            for _ in threads:
                pending.put(stop_token)
            for thread in threads:
                thread.join()

        if not interrupted and state.entries_written == 0:
            warning = {
                'directory': self.base_path,
                'worker_id': -1,
                'error': 'scan completed with zero entries; FTP listing likely failed or returned empty results',
            }
            _LOG.warning('%s', warning['error'])
            state.errors.append(warning)

        flush_state()
        return state
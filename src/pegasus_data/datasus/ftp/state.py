from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json

from ...common.storage import ensure_parent


@dataclass
class ScanState:
    completed_dirs: set[str] = field(default_factory=set)
    in_progress_dirs: set[str] = field(default_factory=set)
    pending_dirs: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    entries_written: int = 0

    def to_dict(self) -> dict:
        return {
            'completed_dirs': sorted(self.completed_dirs),
            'in_progress_dirs': sorted(self.in_progress_dirs),
            'pending_dirs': list(self.pending_dirs),
            'errors': list(self.errors),
            'entries_written': self.entries_written,
        }

    @classmethod
    def from_file(cls, path: str | Path) -> 'ScanState':
        payload = json.loads(Path(path).read_text(encoding='utf-8'))
        return cls(
            completed_dirs=set(payload.get('completed_dirs', payload.get('visited_dirs', []))),
            in_progress_dirs=set(payload.get('in_progress_dirs', [])),
            pending_dirs=list(payload.get('pending_dirs', payload.get('pending', []))),
            errors=list(payload.get('errors', [])),
            entries_written=int(payload.get('entries_written', 0)),
        )

    def save(self, path: str | Path) -> None:
        target = ensure_parent(path)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
from __future__ import annotations

from dataclasses import asdict, dataclass

from ...common.io import read_jsonl


@dataclass(frozen=True)
class ScanDiff:
    added: list[str]
    removed: list[str]
    common: int

    def to_dict(self) -> dict:
        return asdict(self)


def diff_scan_outputs(old_jsonl: str, new_jsonl: str) -> ScanDiff:
    old_paths = {row['full_path'] for row in read_jsonl(old_jsonl)}
    new_paths = {row['full_path'] for row in read_jsonl(new_jsonl)}
    return ScanDiff(
        added=sorted(new_paths - old_paths),
        removed=sorted(old_paths - new_paths),
        common=len(old_paths & new_paths),
    )

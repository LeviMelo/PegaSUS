from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pegasus_data.datasus.discovery.manifest import parse_manifest_line
from pegasus_data.datasus.parsers import get_parser_for_file
from pegasus_data.pegasus.compiler import compile_counts, compile_code_query_counts
from pegasus_data.pegasus.registry import CodeQuery
from pegasus_data.sidra.values.normalize import normalize_value_payload


def run() -> None:
    manifest = parse_manifest_line("ftp://ftp.datasus.gov.br/dissemin/publicos/SINASC/2000_/DADOS/DNAL2412.dbc", scan_id="test")
    assert manifest is not None
    assert manifest.series_prefix == "DN"
    parser = get_parser_for_file(manifest.path)
    assert parser.source_system == "SINASC"

    sidra_rows = normalize_value_payload(
        aggregate_id=475,
        variable_id="93",
        payload=[{"NC": "3550308", "NN": "São Paulo", "D3C": "2024", "D3N": "2024", "D1C": "93", "D1N": "População", "V": "123"}],
    )
    assert sidra_rows[0].value == 123.0

    class FakeRecord:
        def __init__(self, municipality, year, code):
            self.support = {"municipality": municipality, "year": year}
            self.support_role = "notification_residence"
            self.source = {"system": "SINAN"}
            self.event_type = "notification"
            self.code_roles = {"condition": [code]}
            self.subgroups = {}
            self.continuous = {}
            self.annotations = {}
            self.weight = 1.0
            self.quality = {"included": True, "flags": []}
            self.provenance = {}

    records = [FakeRecord("3550308", 2024, "A50"), FakeRecord("3550308", 2024, "A51")]
    counts = compile_counts(records, family="all_notifications", support_keys=["municipality", "year"])
    assert counts.values[0]["value"] == 2.0
    q = CodeQuery(role="condition", system="ICD10", node="A50-A53", descendants=True)
    filtered = compile_code_query_counts(records, family="syphilis_like", query=q, support_keys=["municipality", "year"])
    assert filtered.values[0]["value"] == 2.0


if __name__ == "__main__":
    run()
    print("smoke tests passed")

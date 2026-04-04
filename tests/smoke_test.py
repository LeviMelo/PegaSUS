from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pegasus_data.datasus.discovery.manifest import parse_manifest_line
from pegasus_data.datasus.discovery.docs import build_family_document_registry
from pegasus_data.datasus.inventory import build_dataset_families, build_family_registry, inventory_from_scan_jsonl
from pegasus_data.datasus.profile import build_variable_catalog
from pegasus_data.datasus.translate import build_translation_bundle, emit_translation_grammar, parse_translation_grammar
from pegasus_data.pegasus.compiler import compile_counts, compile_code_query_counts
from pegasus_data.pegasus.registry import CodeQuery
from pegasus_data.sidra.values.normalize import normalize_value_payload


def run() -> None:
    manifest = parse_manifest_line("ftp://ftp.datasus.gov.br/dissemin/publicos/SINASC/2000_/DADOS/DNAL2412.dbc", scan_id="test")
    assert manifest is not None
    assert manifest.series_prefix == "DN"

    with tempfile.TemporaryDirectory() as tmpdir:
        scan_path = Path(tmpdir) / "scan.jsonl"
        scan_rows = [
            {
                "parent_directory": "/dissemin/publicos/SINASC/2000_/DADOS",
                "child_name": "DNAL2412.dbc",
                "full_path": "/dissemin/publicos/SINASC/2000_/DADOS/DNAL2412.dbc",
                "entry_type": "file",
                "size": 10,
                "modified": None,
                "listing_method": "MLSD",
                "scan_timestamp": 0.0,
                "worker_id": 0,
                "error_flags": [],
            },
            {
                "parent_directory": "/dissemin/publicos/SINASC/2000_/DADOS",
                "child_name": "DNAM2412.dbc",
                "full_path": "/dissemin/publicos/SINASC/2000_/DADOS/DNAM2412.dbc",
                "entry_type": "file",
                "size": 10,
                "modified": None,
                "listing_method": "MLSD",
                "scan_timestamp": 0.0,
                "worker_id": 0,
                "error_flags": [],
            },
            {
                "parent_directory": "/dissemin/publicos/SINASC/2000_/DADOS",
                "child_name": "DNBA2412.dbc",
                "full_path": "/dissemin/publicos/SINASC/2000_/DADOS/DNBA2412.dbc",
                "entry_type": "file",
                "size": 10,
                "modified": None,
                "listing_method": "MLSD",
                "scan_timestamp": 0.0,
                "worker_id": 0,
                "error_flags": [],
            },
            {
                "parent_directory": "/dissemin/publicos/SINASC/2000_/DADOS",
                "child_name": "DNRJ2412.dbc",
                "full_path": "/dissemin/publicos/SINASC/2000_/DADOS/DNRJ2412.dbc",
                "entry_type": "file",
                "size": 10,
                "modified": None,
                "listing_method": "MLSD",
                "scan_timestamp": 0.0,
                "worker_id": 0,
                "error_flags": [],
            },
            {
                "parent_directory": "/dissemin/publicos/SINASC/2000_/DADOS",
                "child_name": "DNSP2412.dbc",
                "full_path": "/dissemin/publicos/SINASC/2000_/DADOS/DNSP2412.dbc",
                "entry_type": "file",
                "size": 10,
                "modified": None,
                "listing_method": "MLSD",
                "scan_timestamp": 0.0,
                "worker_id": 0,
                "error_flags": [],
            },
            {
                "parent_directory": "/dissemin/publicos/SINASC/2000_/DOCS",
                "child_name": "layout_sinasc.pdf",
                "full_path": "/dissemin/publicos/SINASC/2000_/DOCS/layout_sinasc.pdf",
                "entry_type": "file",
                "size": 10,
                "modified": None,
                "listing_method": "MLSD",
                "scan_timestamp": 0.0,
                "worker_id": 0,
                "error_flags": [],
            },
        ]
        scan_path.write_text('\n'.join(json.dumps(row) for row in scan_rows) + '\n', encoding='utf-8')
        doc_root = Path(tmpdir) / "docs"
        doc_root.mkdir()
        (doc_root / "layout_sinasc.pdf").write_text("SINASC layout RACACOR CODMUNRES DTOBITO", encoding='utf-8')
        inventory = inventory_from_scan_jsonl(str(scan_path))
        assert len(inventory) == 6
        assert inventory[0].series_prefix == "DN"

        families = build_dataset_families(inventory, schema_signatures={
            "/dissemin/publicos/SINASC/2000_/DADOS/DNAL2412.dbc": "abc123",
        })
        assert len(families) == 1
        family_payload = [row.to_dict() for row in families]
        assert family_payload[0]["family_id"].startswith("SINASC:DN")

        profiles = [
            {
                "path": "/dissemin/publicos/SINASC/2000_/DADOS/DNAL2412.dbc",
                "schema_signature": "abc123",
                "field_profiles": [
                    {"name": "RACACOR", "primitive_type": "categorical_code", "samples": ["1", "4"], "signals": []},
                    {"name": "CODMUNRES", "primitive_type": "municipality_code", "samples": ["3550308"], "signals": ["municipality_name_hint"]},
                ],
            },
            {
                "path": "/dissemin/publicos/SINASC/2000_/DADOS/DNBR2412.dbc",
                "schema_signature": "def456",
                "field_profiles": [
                    {"name": "RACACOR", "primitive_type": "categorical_code", "samples": ["1", "2"], "signals": []},
                    {"name": "DTOBITO", "primitive_type": "date", "samples": ["20240115"], "signals": ["date_name_hint"]},
                ],
            },
        ]
        family_registry = build_family_registry(family_payload, profile_rows=profiles)
        assert family_registry[0].variable_count == 2

        doc_registry = build_family_document_registry(family_payload, doc_root=doc_root, max_chars=200)
        assert doc_registry[0].local_path is not None

        variable_catalog = build_variable_catalog(profiles, families=family_payload)
        variable_rows = [row.to_dict() for row in variable_catalog]
        raca = next(row for row in variable_rows if row["variable"] == "RACACOR")
        assert raca["file_count"] == 2

        grammar = parse_translation_grammar(
            "$ RACACOR cat raça_cor\n"
            "~ COR_RACA\n"
            "= 1 branca\n"
            "= 4 parda\n"
            "@ SINASC:DN DTOBITO date data_obito\n"
            "> date8\n"
            "% doc:sinasc\n"
        )
        emitted = emit_translation_grammar(grammar)
        reparsed = parse_translation_grammar(emitted)
        assert reparsed.resolve("RACACOR") is not None
        assert reparsed.resolve("COR_RACA") is not None
        coverage = reparsed.coverage_for_variables(["RACACOR", "DTOBITO", "IGNORADO"], scopes=["SINASC:DN"])
        assert coverage["covered_count"] == 2
        assert coverage["missing"] == ["IGNORADO"]

        bundle = build_translation_bundle(
            family_payload[0],
            profiles,
            variable_rows,
            document_registry=[row.to_dict() for row in doc_registry],
        )
        assert "RACACOR" in bundle.prompt_text
        assert "Return grammar only." in bundle.prompt_text
        assert "DOC_EXCERPTS" in bundle.prompt_text

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

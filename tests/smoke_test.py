from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pegasus_data.datasus.discovery.manifest import parse_manifest_line
from pegasus_data.datasus.discovery.docs import build_family_document_registry
from pegasus_data.datasus.decode.inspect import inspect_file
from pegasus_data.datasus.fetch import plan_family_candidate_downloads, select_family_candidates
from pegasus_data.datasus.ftp.scanner import DatasusFtpScanner, ScanEntry
from pegasus_data.datasus.ftp.state import ScanState
from pegasus_data.datasus.inventory import build_dataset_families, build_family_registry, inventory_from_scan_jsonl
from pegasus_data.datasus.profile import build_family_similarity_report, build_variable_catalog, build_variable_similarity_report, profile_file
from pegasus_data.datasus.translate import build_translation_bundle, emit_translation_grammar, parse_translation_grammar
from pegasus_data.pegasus.compiler import compile_counts, compile_code_query_counts
from pegasus_data.pegasus.registry import CodeQuery
from pegasus_data.sidra.values.normalize import normalize_value_payload


def run() -> None:
    scanner = DatasusFtpScanner()
    scanner._mlsd_entries = lambda ftp, directory: []  # type: ignore[method-assign]
    scanner._list_entries = lambda ftp, directory: [  # type: ignore[method-assign]
        ScanEntry(
            parent_directory=directory,
            child_name="DNAL2412.dbc",
            full_path=f"{directory}/DNAL2412.dbc",
            entry_type="file",
            size=10,
            modified=None,
            listing_method="LIST",
            scan_timestamp=0.0,
            worker_id=0,
            error_flags=[],
        )
    ]
    scanner._nlst_entries = lambda ftp, directory: []  # type: ignore[method-assign]
    fallback_rows = scanner._list_directory(object(), "/dissemin/publicos/SINASC/2000_/DADOS")
    assert fallback_rows and fallback_rows[0].listing_method == "LIST"

    with tempfile.TemporaryDirectory() as tmpdir:
        checkpoint = Path(tmpdir) / "scanstate.json"
        ScanState(
            visited_dirs={"/dissemin/publicos"},
            pending_dirs=[],
            errors=[],
            entries_written=0,
        ).save(checkpoint)
        reset_state = scanner._load_or_initialize_state(checkpoint)
        assert reset_state.pending_dirs == ["/dissemin/publicos"]
        assert reset_state.visited_dirs == set()

    manifest = parse_manifest_line("ftp://ftp.datasus.gov.br/dissemin/publicos/SINASC/2000_/DADOS/DNAL2412.dbc", scan_id="test")
    assert manifest is not None
    assert manifest.series_prefix == "DN"
    wrapped_manifest = parse_manifest_line(
        "ftp://ftp.datasus.gov.br/dissemin/publicos/Dados_Abertos/SINAN/Malaria/json/MALABR17.json.zip",
        scan_id="test",
    )
    assert wrapped_manifest is not None
    assert wrapped_manifest.series_prefix == "MALA"
    assert wrapped_manifest.primary_extension == ".json"
    assert wrapped_manifest.format_family == "json"

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
        assert len(family_payload[0]["member_files"]) == 5

        profiles = [
            {
                "path": "/dissemin/publicos/SINASC/2000_/DADOS/DNAL2412.dbc",
                "schema_signature": "abc123",
                "field_profiles": [
                    {"name": "RACACOR", "primitive_type": "categorical_code", "samples": ["1", "4"], "signals": []},
                    {"name": "CODMUNRES", "primitive_type": "municipality_code", "samples": ["3550308"], "signals": ["municipality_name_hint"]},
                    {"name": "DTOBITO", "primitive_type": "date", "samples": ["20240115"], "signals": ["date_name_hint"]},
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
            {
                "path": "/dissemin/publicos/SIM/2000_/DADOS/DOAL2412.dbc",
                "schema_signature": "ghi789",
                "field_profiles": [
                    {"name": "RACACOR", "primitive_type": "categorical_code", "samples": ["1", "4"], "signals": []},
                    {"name": "CODMUNRESI", "primitive_type": "municipality_code", "samples": ["3550308"], "signals": ["municipality_name_hint"]},
                    {"name": "DTOBITO", "primitive_type": "date", "samples": ["20240115"], "signals": ["date_name_hint"]},
                ],
            },
        ]
        family_payload.append({
            "family_id": "SIM:DO",
            "system_guess": "SIM",
            "series_prefix": "DO",
            "partition_type": "State-Partitioned",
            "date_format": "YYMM",
            "time_range_display": "Dec 2024 to Dec 2024",
            "file_count": 1,
            "member_files": ["/dissemin/publicos/SIM/2000_/DADOS/DOAL2412.dbc"],
            "files": ["/dissemin/publicos/SIM/2000_/DADOS/DOAL2412.dbc"],
            "source_paths": ["/dissemin/publicos/SIM/2000_/DADOS"],
            "geo_coverage": ["AL"],
            "path_semantics": {"/dissemin/publicos/SIM/2000_/DADOS": "[Primary]"},
            "associated_docs": [],
            "schema_signatures": ["ghi789"],
        })
        family_registry = build_family_registry(family_payload, profile_rows=profiles)
        assert family_registry[0].variable_count == 3
        assert family_registry[0].member_files[0].endswith("DNAL2412.dbc")

        selection = select_family_candidates(family_registry[0].to_dict(), max_data_files=2, max_docs=1)
        assert selection.selected_data_files
        assert selection.selected_data_files[0].primary_extension == ".dbc"
        download_plans = plan_family_candidate_downloads(selection.to_dict(), asset_kind="data", root=Path(tmpdir) / "raw")
        assert "dissemin/publicos/SINASC/2000_/DADOS/" in download_plans[0].target_path
        assert download_plans[0].target_path.endswith(".dbc")

        malaria_family = {
            "family_id": "SINAN:MALA",
            "system_guess": "SINAN",
            "series_prefix": "MALA",
            "partition_type": "Nation-Wide",
            "date_format": "YY",
            "time_range_display": "2017 to 2018",
            "member_files": [
                "/dissemin/publicos/Dados_Abertos/SINAN/Malaria/json/MALABR17.json.zip",
                "/dissemin/publicos/Dados_Abertos/SINAN/Malaria/json/MALABR18.json.zip",
            ],
            "files": [
                "/dissemin/publicos/Dados_Abertos/SINAN/Malaria/json/MALABR17.json.zip",
                "/dissemin/publicos/Dados_Abertos/SINAN/Malaria/json/MALABR18.json.zip",
            ],
            "path_semantics": {
                "/dissemin/publicos/Dados_Abertos/SINAN/Malaria/json": "[Primary]",
            },
            "associated_docs": [],
        }
        wrapped_selection = select_family_candidates(malaria_family, max_data_files=1, max_docs=0)
        assert wrapped_selection.selected_data_files[0].source_path.endswith(".json.zip")
        assert wrapped_selection.selected_data_files[0].format_family == "json"

        doc_registry = build_family_document_registry(family_payload, doc_root=doc_root, max_chars=200)
        assert doc_registry[0].local_path is not None

        json_zip_path = Path(tmpdir) / "MALABR18.json.zip"
        with zipfile.ZipFile(json_zip_path, "w") as archive:
            archive.writestr("MALABR18.json", json.dumps([
                {"UF": "BR", "ANO": 2018, "CASOS": 10},
                {"UF": "BR", "ANO": 2018, "CASOS": 12},
            ]))
        preview = inspect_file(str(json_zip_path), sample_rows=2)
        assert preview.file_format == "zip:json"
        assert "CASOS" in preview.field_names
        generic_profile = profile_file(
            str(json_zip_path),
            sample_rows=2,
            source_path="/dissemin/publicos/Dados_Abertos/SINAN/Malaria/json/MALABR18.json.zip",
            local_path=str(json_zip_path),
        )
        assert generic_profile.source_path.endswith(".json.zip")
        assert generic_profile.local_path == str(json_zip_path)
        assert generic_profile.field_names == ["ANO", "CASOS", "UF"]

        variable_catalog = build_variable_catalog(profiles, families=family_payload)
        variable_rows = [row.to_dict() for row in variable_catalog]
        raca = next(row for row in variable_rows if row["variable"] == "RACACOR")
        assert raca["file_count"] == 3

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

        family_similarity = build_family_similarity_report(profiles, family_payload, similarity_threshold=0.5)
        assert family_similarity["family_pairs"]
        variable_similarity = build_variable_similarity_report(
            profiles,
            family_payload,
            family_similarity_threshold=0.5,
            name_similarity_threshold=0.8,
            value_similarity_threshold=1.0,
        )
        assert "variable_clusters" in variable_similarity

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

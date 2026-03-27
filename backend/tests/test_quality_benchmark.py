import json
from pathlib import Path

from scripts.benchmark_quality import load_fixture_manifest


def test_load_fixture_manifest_resolves_relative_paths(tmp_path: Path) -> None:
    fixture_root = tmp_path / "quality"
    fixture_root.mkdir(parents=True)
    manifest_path = fixture_root / "manifest.json"
    sample_path = fixture_root / "cases" / "demo" / "sample.mp4"
    sample_path.parent.mkdir(parents=True)
    sample_path.write_bytes(b"video")

    manifest_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "name": "demo",
                        "input_path": "cases/demo/sample.mp4",
                        "processing_mode": "camera",
                        "min_pages": 1,
                        "max_pages": 4,
                        "max_deleted_like_pages": 0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    cases = load_fixture_manifest(manifest_path)

    assert len(cases) == 1
    assert cases[0].name == "demo"
    assert cases[0].input_path == sample_path.resolve()
    assert cases[0].min_pages == 1
    assert cases[0].max_deleted_like_pages == 0

Quality fixture corpus

Place real sample videos for benchmark evaluation in this folder tree and register them in `manifest.json`.

Recommended layout:

- `cases/book_turn_clean/sample.mp4`
- `cases/book_turn_blurry/sample.mp4`
- `cases/report_off_axis/sample.mp4`
- `cases/cluttered_desk/sample.mp4`

Each case should be a short representative clip for one failure mode or one expected-good flow.

Benchmark usage:

```bash
cd backend
python scripts/benchmark_quality.py
```

Optional explicit manifest path:

```bash
python scripts/benchmark_quality.py tests/fixtures/quality/manifest.json
```

Manifest fields:

- `name`: unique case id
- `input_path`: path relative to this manifest file
- `processing_mode`: `camera` or `screen`
- `min_pages`: minimum acceptable extracted page count
- `max_pages`: maximum acceptable extracted page count
- `max_deleted_like_pages`: maximum weak/low-confidence kept pages tolerated
- `notes`: optional freeform context

The benchmark currently skips cases whose media files are missing, so the corpus can be staged gradually.

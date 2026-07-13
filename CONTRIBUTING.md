# Contributing to Vid2PDF

Thanks for your interest in contributing! Vid2PDF reconstructs clean PDFs from
screen recordings of documents. Contributions of all kinds are welcome: bug
reports, pipeline-quality improvements, UI polish, docs, and tests.

## Development setup

### Prerequisites

- Python 3.12+
- Node.js 18+
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) on `PATH` (text extraction)
- [Tectonic](https://tectonic-typesetting.github.io/) on `PATH` (LaTeX → PDF compilation)

Both binaries are auto-resolved from `PATH` and standard install locations; you
can override with `tesseract_cmd` / `tectonic_cmd` in `backend/app/core/settings.py`.

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate     # Windows
source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend expects the API at `http://localhost:8000` (configurable via
`VITE_API_BASE_URL`).

## Running tests

```bash
# Backend (from backend/)
python -m pytest tests -q

# Frontend type-check + production build (from frontend/)
npm run build
```

Please make sure both pass before opening a pull request.

## Project layout

- `backend/app/processing/` — the reconstruction pipeline (sampling,
  segmentation, frame selection, dedup, OCR, LaTeX/PDF export). See the
  README for a stage-by-stage overview.
- `backend/app/services/job_service.py` — job state, background execution,
  persistence.
- `frontend/src/features/` — dashboard, review board, page editor.

## Guidelines

- Keep changes focused; one logical change per pull request.
- Add or update tests for behavior changes — especially in
  `backend/tests/test_ocr_latex.py` and `backend/tests/test_processing_quality.py`
  for pipeline-quality work.
- Pipeline heuristics (thresholds in `backend/app/core/settings.py`) are
  sensitive: if you tune them, include before/after results on a sample video
  in the PR description.
- Match the existing code style (type hints in Python, strict TypeScript in
  the frontend). No new dependencies without discussion in an issue first.
- Do not commit files under `backend/data/` (job artifacts, uploads) — they
  are gitignored for a reason.

## Reporting bugs

Open an issue with:

- what you did (video type, processing mode, steps)
- what you expected vs. what happened
- backend logs if relevant (uvicorn console output)

If the bug involves extraction quality, the debug artifacts under
`backend/data/jobs/<job-id>/debug/` (kept/rejected frames and
`pipeline_report.json`) are very helpful.

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).

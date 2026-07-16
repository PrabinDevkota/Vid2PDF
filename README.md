# Vid2PDF

[![CI](https://github.com/PrabinDevkota/Vid2PDF/actions/workflows/ci.yml/badge.svg)](https://github.com/PrabinDevkota/Vid2PDF/actions/workflows/ci.yml)

Vid2PDF reconstructs a clean PDF from a screen recording of a digital document being viewed page by page.

It is structured around a document reconstruction pipeline rather than generic frame dumping:

1. upload one or more screen-recorded document videos (up to 10 per batch), or paste a video URL — YouTube and any yt-dlp-supported site, plus direct links
2. sample frames from the video (optionally limited to a start/end time range)
3. detect stable page-view segments (with adjustable detection sensitivity)
4. pick the clearest representative frame for each page
5. remove duplicates and weak pages — the strongest rejected candidates are kept and can be restored from the Rejected tab
6. generate previews for review
7. extract text from unique page frames (OCR)
8. let the user review and edit pages: delete, rotate, straighten (manual or auto-deskew), crop (manual or auto-crop to the detected paper), zoom, draw, highlight, place text, blur or black out regions, adjust brightness/contrast, apply cleanup filters (enhance / grayscale / B&W), correct OCR text by hand — with full undo/redo (Ctrl+Z / Ctrl+Y) and keyboard shortcuts for review (press `?` in the app)
9. export a lossless image PDF (image-sized, A4, or Letter pages), a LaTeX-typeset text PDF (via Tectonic), a searchable PDF (pixel-identical page images with an invisible OCR text layer), or combine several sessions into a single PDF

Jobs can be cancelled while queued or processing, progress streams live over
server-sent events, and the UI supports light, dark, and system themes.

## Repo layout

```text
Vid2PDF/
├─ frontend/                  # React + TypeScript app
├─ backend/
│  ├─ app/
│  │  ├─ api/
│  │  ├─ core/
│  │  ├─ models/
│  │  ├─ processing/
│  │  ├─ schemas/
│  │  ├─ services/
│  │  └─ main.py
│  └─ tests/
└─ README.md
```

## Architecture

### Frontend

The frontend is a Vite React app focused on:

- uploading recordings (single or batch) or pasting a video URL, with an optional processing time range and a camera page style (cleaned scan or original color)
- reviewing extracted pages before export (delete, rotate, reorder, restore rejected candidates, reprocess with different sensitivity, keyboard shortcuts)
- a page editor with zoom, undo/redo, auto-crop, auto-straighten, drawing, highlighting, text, blur/black-out redaction, brightness/contrast, and cleanup filters
- per-page OCR confidence badges and inline OCR text correction (useful for handwriting)
- exporting image PDF (with page-size options), text PDF, searchable PDF, and combined multi-session PDFs
- live job progress over server-sent events (with polling fallback) and a light/dark/system theme toggle

### Backend

The backend uses FastAPI and is organized around a reconstruction pipeline:

- upload endpoint creates a processing job
- job service manages persisted job state
- OpenCV pipeline stages extract unique pages
- Tesseract OCR extracts text from each unique page
- Tectonic compiles OCR text into a formatted LaTeX PDF

### Processing pipeline

Pipeline stages live in `backend/app/processing/`

- `downloader.py`: video download from URL (yt-dlp)
- `sampler.py`: frame sampling
- `segmenter.py`: stable segment detection
- `selector.py`: best-frame selection
- `deduper.py`: duplicate filtering
- `preview.py`: preview preparation
- `ocr.py`: Tesseract text extraction
- `editor.py`: page transforms and cleanup filters
- `latex_builder.py` / `tectonic_exporter.py`: text PDF export
- `exporter.py`: image PDF export
- `searchable_exporter.py`: searchable PDF export (image pages + invisible OCR text layer)
- `pipeline.py`: orchestration

## System dependencies

In addition to Python packages, the host needs:

- **Tesseract OCR** on `PATH` (used for text extraction)
- **Tectonic** on `PATH` (used to compile LaTeX text PDFs)
- **FFmpeg** on `PATH` (optional — lets yt-dlp merge separate video+audio streams for higher-quality URL downloads; without it, single-file formats are used)

Windows install tips:

- Tesseract: install from https://github.com/UB-Mannheim/tesseract/wiki
- Tectonic: install from https://tectonic-typesetting.github.io/ or via `cargo install tectonic`

Optional: set `tesseract_cmd` / `tectonic_cmd` in settings if binaries are not on `PATH`.

## Local development

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## API

- `GET /health`
- `GET /api/events` — server-sent events stream of job state changes
- `GET /api/jobs`
- `GET /api/jobs/{job_id}`
- `POST /api/jobs/upload` — accepts optional `trim_start` / `trim_end` seconds
- `POST /api/jobs/from-url` — create a job from a video URL (yt-dlp), same trim options
- `POST /api/jobs/{job_id}/reprocess` — re-run page detection with a different sensitivity or trim range
- `POST /api/jobs/{job_id}/cancel` — cancel a queued or processing job
- `POST /api/jobs/{job_id}/rejected/{rejected_id}/restore` — promote a pipeline-rejected frame to a page
- `DELETE /api/jobs/{job_id}`
- `POST /api/jobs/{job_id}/export` — image PDF
- `POST /api/jobs/{job_id}/export/text` — OCR + LaTeX/Tectonic text PDF
- `POST /api/jobs/{job_id}/export/searchable` — image PDF with invisible OCR text layer

## Assumptions

- v1 is single-video in, PDF out (image, text, and searchable variants)
- target inputs are screen recordings of digital documents (camera mode also supported)
- text PDF fidelity prioritizes content completeness over perfect layout recreation
- job state is persisted to JSON under `backend/data`

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for setup,
testing, and pull request guidelines. Please also read the
[Code of Conduct](CODE_OF_CONDUCT.md).

## License

Vid2PDF is open source under the [MIT License](LICENSE).

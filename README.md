# Vid2PDF

Vid2PDF reconstructs a clean PDF from a screen recording of a digital document being viewed page by page.

It is structured around a document reconstruction pipeline rather than generic frame dumping:

1. upload one screen-recorded document video (or paste a video URL — YouTube and any yt-dlp-supported site, plus direct links)
2. sample frames from the video
3. detect stable page-view segments (with adjustable detection sensitivity)
4. pick the clearest representative frame for each page
5. remove duplicates and weak pages
6. generate previews for review
7. extract text from unique page frames (OCR)
8. let the user delete, rotate, reorder, and clean up pages (enhance / grayscale / B&W filters)
9. export an image PDF, a LaTeX-typeset text PDF (via Tectonic), and/or a searchable PDF (original page images with an invisible OCR text layer)

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

- uploading one screen recording or pasting a video URL
- reviewing extracted pages before export (delete, rotate, reorder, cleanup filters, reprocess with different sensitivity)
- exporting image PDF, text PDF, and searchable PDF artifacts

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
- `GET /api/jobs`
- `GET /api/jobs/{job_id}`
- `POST /api/jobs/upload`
- `POST /api/jobs/from-url` — create a job from a video URL (yt-dlp)
- `POST /api/jobs/{job_id}/reprocess` — re-run page detection with a different sensitivity
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

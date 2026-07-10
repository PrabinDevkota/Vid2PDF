# Vid2PDF

Vid2PDF reconstructs a clean PDF from a screen recording of a digital document being viewed page by page.

It is structured around a document reconstruction pipeline rather than generic frame dumping:

1. upload one screen-recorded document video
2. sample frames from the video
3. detect stable page-view segments
4. pick the clearest representative frame for each page
5. remove duplicates and weak pages
6. generate previews for review
7. extract text from unique page frames (OCR)
8. let the user delete, rotate, and reorder pages
9. export an image PDF and/or a searchable text PDF (LaTeX via Tectonic)

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

- uploading one screen recording
- reviewing extracted pages before export
- exporting image PDF and text PDF artifacts

### Backend

The backend uses FastAPI and is organized around a reconstruction pipeline:

- upload endpoint creates a processing job
- job service manages persisted job state
- OpenCV pipeline stages extract unique pages
- Tesseract OCR extracts text from each unique page
- Tectonic compiles OCR text into a formatted LaTeX PDF

### Processing pipeline

Pipeline stages live in `backend/app/processing/`

- `sampler.py`: frame sampling
- `segmenter.py`: stable segment detection
- `selector.py`: best-frame selection
- `deduper.py`: duplicate filtering
- `preview.py`: preview preparation
- `ocr.py`: Tesseract text extraction
- `latex_builder.py` / `tectonic_exporter.py`: text PDF export
- `exporter.py`: image PDF export
- `pipeline.py`: orchestration

## System dependencies

In addition to Python packages, the host needs:

- **Tesseract OCR** on `PATH` (used for text extraction)
- **Tectonic** on `PATH` (used to compile LaTeX text PDFs)

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
- `POST /api/jobs/{job_id}/export` — image PDF
- `POST /api/jobs/{job_id}/export/text` — OCR + LaTeX/Tectonic text PDF

## Assumptions

- v1 is single-video in, dual PDF out (image + text)
- target inputs are screen recordings of digital documents (camera mode also supported)
- text PDF fidelity prioritizes content completeness over perfect layout recreation
- job state is persisted to JSON under `backend/data`

# Vid2PDF

Vid2PDF reconstructs a clean PDF from a screen recording of a digital document being viewed page by page.

It is structured around a document reconstruction pipeline rather than generic frame dumping:

1. upload one screen-recorded document video
2. sample frames from the video
3. detect stable page-view segments
4. pick the clearest representative frame for each page
5. remove duplicates and weak pages
6. generate previews for review
7. let the user delete, rotate, and reorder pages
8. export a final PDF

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

- explaining the reconstruction pipeline
- uploading one screen recording
- reviewing extracted pages before export

### Backend

The backend uses FastAPI and is organized around a reconstruction pipeline:

- upload endpoint creates a processing job
- job service manages in-memory v1 job state
- processing modules represent the future computer-vision stages
- job endpoints return page previews and status for review UI

### Processing pipeline

Pipeline stages live in `backend/app/processing/`

- `sampler.py`: frame sampling
- `segmenter.py`: stable segment detection
- `selector.py`: best-frame selection
- `deduper.py`: duplicate filtering
- `preview.py`: preview preparation
- `exporter.py`: PDF export boundary
- `pipeline.py`: orchestration

## Implemented now

- clean full-stack scaffold
- frontend foundation for upload and review
- FastAPI backend with upload/job/export endpoints
- in-memory job orchestration
- realistic processing-module placeholders
- starter test and setup files

## Placeholder for later

- real FFmpeg/OpenCV frame extraction
- page-change and stable-segment detection
- blur/sharpness/image-quality scoring
- similarity-based duplicate removal
- preview image generation and persistence
- actual PDF rendering/export
- database, queueing, auth, and cloud deployment

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
- `POST /api/jobs/{job_id}/export`

## Assumptions

- v1 is single-video in, single-PDF out
- target inputs are screen recordings of digital documents, not camera footage
- OCR/searchable output is deferred
- in-memory job state is acceptable for initial development

## Recommended next steps

1. Replace placeholder frame sampling with real video decoding.
2. Implement frame-difference based page segment detection.
3. Add frame quality scoring and best-frame selection heuristics.
4. Persist preview assets and edited page state.
5. Generate the final PDF from reviewed pages.

Other works on progress...

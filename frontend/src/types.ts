export type JobStatus = "queued" | "processing" | "ready" | "failed" | "cancelled";
export type StageStatus = "pending" | "processing" | "complete" | "failed";
export type PageStatus = "active" | "deleted";
export type ExportStatus = "idle" | "processing" | "ready" | "failed";
export type ProcessingMode = "screen" | "camera";
export type OcrStatus = "pending" | "ready" | "failed" | "empty";
export type PageFilter = "none" | "enhance" | "grayscale" | "bw";
export type Sensitivity = "fewer" | "balanced" | "more";

export interface EditPoint {
  x: number;
  y: number;
}

export interface CropBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface DrawStroke {
  color: string;
  width: number;
  points: EditPoint[];
  /** 1 = opaque pen; < 1 renders as a translucent highlighter stroke. */
  opacity: number;
}

export interface TextAnnotation {
  text: string;
  x: number;
  y: number;
  color: string;
  fontSize: number;
}

export type RegionMode = "blur" | "fill";

export interface BlurRegion {
  x: number;
  y: number;
  width: number;
  height: number;
  intensity: number;
  /** "blur" softens the region; "fill" redacts it with a solid color. */
  mode: RegionMode;
  fillColor: string;
}

export interface PageEdits {
  rotation: number;
  /** Small straightening angle in degrees (-15..15). */
  fineRotation: number;
  crop: CropBox | null;
  filter: PageFilter;
  /** -100..100; 0 leaves the page untouched. */
  brightness: number;
  contrast: number;
  strokes: DrawStroke[];
  texts: TextAnnotation[];
  blurRegions: BlurRegion[];
}

export type PageSizeOption = "auto" | "a4" | "letter";
export type CameraOutput = "cleaned" | "color";

export interface OcrBlock {
  text: string;
  confidence: number;
  top: number;
  left: number;
}

export interface ProgressState {
  percent: number;
  message: string;
}

export interface ProcessingStage {
  key: string;
  label: string;
  status: StageStatus;
  progressPercent: number;
  startedAt: string | null;
  completedAt: string | null;
}

export interface ExtractedPage {
  id: string;
  jobId: string;
  orderIndex: number;
  pageNumber: number;
  previewLabel: string;
  thumbnailUrl: string | null;
  imageUrl: string | null;
  sourceImageUrl: string | null;
  sharpnessScore: number;
  segmentStart: number;
  segmentEnd: number;
  sourceFrameIndex: number;
  sourceTimestamp: number;
  manual: boolean;
  rotation: number;
  status: PageStatus;
  deleted: boolean;
  edits: PageEdits;
  ocrText: string | null;
  ocrBlocks: OcrBlock[];
  ocrStatus: OcrStatus;
  ocrError: string | null;
  ocrConfidence: number | null;
}

export interface RejectedFrame {
  id: string;
  timestamp: number;
  sourceFrameIndex: number;
  reason: string;
  score: number;
  imageUrl: string | null;
  thumbnailUrl: string | null;
}

export interface ExportState {
  status: ExportStatus;
  progressPercent: number;
  filename: string | null;
  downloadUrl: string | null;
  texUrl?: string | null;
  requestedAt: string | null;
  completedAt: string | null;
  error: string | null;
}

export interface ProcessingJob {
  id: string;
  filename: string;
  processingMode: ProcessingMode;
  sourceVideoUrl: string | null;
  sourceUrl?: string | null;
  ocrLanguage?: string;
  sensitivity?: Sensitivity;
  cameraOutput?: CameraOutput;
  trimStart?: number | null;
  trimEnd?: number | null;
  videoWidth?: number | null;
  videoHeight?: number | null;
  status: JobStatus;
  createdAt: string;
  updatedAt: string;
  startedAt: string | null;
  completedAt: string | null;
  currentStageKey: string | null;
  progress: ProgressState;
  notes: string[];
  stages: ProcessingStage[];
  pages: ExtractedPage[];
  rejectedFrames?: RejectedFrame[];
  export: ExportState;
  textExport: ExportState;
  searchableExport: ExportState;
}

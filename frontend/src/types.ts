export type JobStatus = "queued" | "processing" | "ready" | "failed";
export type StageStatus = "pending" | "processing" | "complete" | "failed";
export type PageStatus = "active" | "deleted";
export type ExportStatus = "idle" | "processing" | "ready" | "failed";
export type ProcessingMode = "screen" | "camera";

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
}

export interface TextAnnotation {
  text: string;
  x: number;
  y: number;
  color: string;
  fontSize: number;
}

export interface BlurRegion {
  x: number;
  y: number;
  width: number;
  height: number;
  intensity: number;
}

export interface PageEdits {
  rotation: number;
  crop: CropBox | null;
  strokes: DrawStroke[];
  texts: TextAnnotation[];
  blurRegions: BlurRegion[];
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
}

export interface ExportState {
  status: ExportStatus;
  progressPercent: number;
  filename: string | null;
  downloadUrl: string | null;
  requestedAt: string | null;
  completedAt: string | null;
  error: string | null;
}

export interface ProcessingJob {
  id: string;
  filename: string;
  processingMode: ProcessingMode;
  sourceVideoUrl: string | null;
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
  export: ExportState;
}

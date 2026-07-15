import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Crop,
  EyeOff,
  Highlighter,
  Loader2,
  Pencil,
  RotateCcw,
  RotateCw,
  Type,
  Wand2,
  X,
} from "lucide-react";
import { fetchCropSuggestion, resolveArtifactUrl } from "../../lib/api";
import type {
  BlurRegion,
  CropBox,
  DrawStroke,
  EditPoint,
  ExtractedPage,
  PageEdits,
  PageFilter,
  RegionMode,
  TextAnnotation,
} from "../../types";

type EditorTool = "crop" | "draw" | "highlight" | "text" | "blur";

const HIGHLIGHT_OPACITY = 0.35;

interface PageEditorModalProps {
  page: ExtractedPage | null;
  isSaving: boolean;
  onClose: () => void;
  onSave: (edits: PageEdits) => Promise<void>;
}

interface DragState {
  start: EditPoint;
  current: EditPoint;
}

const MAX_CANVAS_WIDTH = 920;
const MAX_CANVAS_HEIGHT = 640;

const TOOL_CONFIG: { key: EditorTool; label: string; hint: string; Icon: typeof Crop }[] = [
  { key: "crop", label: "Crop", hint: "Drag to select the area to keep.", Icon: Crop },
  { key: "draw", label: "Draw", hint: "Draw freehand on the page.", Icon: Pencil },
  {
    key: "highlight",
    label: "Highlight",
    hint: "Drag a translucent marker over important lines.",
    Icon: Highlighter,
  },
  { key: "text", label: "Text", hint: "Click on the page to place text.", Icon: Type },
  {
    key: "blur",
    label: "Hide",
    hint: "Drag a rectangle to blur or black out anything sensitive.",
    Icon: EyeOff,
  },
];

const TOOL_CURSOR: Record<EditorTool, string> = {
  crop: "crosshair",
  blur: "crosshair",
  draw: "crosshair",
  highlight: "crosshair",
  text: "text",
};

export function PageEditorModal({
  page,
  isSaving,
  onClose,
  onSave,
}: PageEditorModalProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const [edits, setEdits] = useState<PageEdits | null>(null);
  const [tool, setTool] = useState<EditorTool>("crop");
  const [drawColor, setDrawColor] = useState("#d9480f");
  const [drawWidth, setDrawWidth] = useState(6);
  const [highlightColor, setHighlightColor] = useState("#facc15");
  const [highlightWidth, setHighlightWidth] = useState(16);
  const [blurIntensity, setBlurIntensity] = useState(18);
  const [regionMode, setRegionMode] = useState<RegionMode>("blur");
  const [fillColor, setFillColor] = useState("#000000");
  const [textValue, setTextValue] = useState("Confidential");
  const [textColor, setTextColor] = useState("#111111");
  const [textSize, setTextSize] = useState(28);
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [activeStroke, setActiveStroke] = useState<DrawStroke | null>(null);
  const [imageReady, setImageReady] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isAutoCropping, setIsAutoCropping] = useState(false);
  const [autoCropNote, setAutoCropNote] = useState<string | null>(null);

  useEffect(() => {
    if (!page) {
      setEdits(null);
      return;
    }
    setEdits(structuredClone(page.edits));
    setTool("crop");
    setDragState(null);
    setActiveStroke(null);
    setImageReady(false);
    setLoadError(null);
    setIsAutoCropping(false);
    setAutoCropNote(null);

    const sourceUrl = resolveArtifactUrl(page.sourceImageUrl ?? page.imageUrl);
    if (!sourceUrl) {
      setLoadError("Source page image is unavailable.");
      return;
    }

    const image = new Image();
    // The page image lives on the API origin (e.g. :8000 vs the app's :5173).
    // Without a CORS-enabled load the canvas becomes tainted and getImageData
    // throws a SecurityError, which broke the cleanup-filter previews.
    image.crossOrigin = "anonymous";
    image.onload = () => {
      imageRef.current = image;
      setImageReady(true);
    };
    image.onerror = () => {
      setLoadError("Page image could not be loaded for editing.");
    };
    image.src = sourceUrl;
  }, [page]);

  const handleClose = useCallback(() => {
    if (!isSaving) {
      onClose();
    }
  }, [isSaving, onClose]);

  useEffect(() => {
    if (!page) {
      return;
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        handleClose();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [page, handleClose]);

  const workingSize = useMemo(() => {
    const image = imageRef.current;
    if (!image || !edits) {
      return { width: 1, height: 1, scale: 1 };
    }
    const rotatedWidth = edits.rotation % 180 === 0 ? image.naturalWidth : image.naturalHeight;
    const rotatedHeight = edits.rotation % 180 === 0 ? image.naturalHeight : image.naturalWidth;
    const croppedWidth = edits.crop?.width ?? rotatedWidth;
    const croppedHeight = edits.crop?.height ?? rotatedHeight;
    const scale = Math.min(
      1,
      MAX_CANVAS_WIDTH / Math.max(croppedWidth, 1),
      MAX_CANVAS_HEIGHT / Math.max(croppedHeight, 1),
    );
    return {
      width: Math.max(1, Math.round(croppedWidth * scale)),
      height: Math.max(1, Math.round(croppedHeight * scale)),
      scale,
    };
    // imageReady matters: the memo reads imageRef.current, which is only
    // populated once the source image finishes loading.
  }, [edits, imageReady]);

  useEffect(() => {
    if (!page || !edits || !imageReady || !canvasRef.current || !imageRef.current) {
      return;
    }
    renderEditorCanvas({
      canvas: canvasRef.current,
      image: imageRef.current,
      edits,
      scale: workingSize.scale,
      dragState,
      activeStroke,
      tool,
    });
  }, [page, edits, imageReady, workingSize, dragState, activeStroke, tool]);

  if (!page || !edits) {
    return null;
  }

  const activeTool = TOOL_CONFIG.find((item) => item.key === tool);
  const hasAnnotations =
    edits.strokes.length > 0 || edits.texts.length > 0 || edits.blurRegions.length > 0;

  function transformEdits(nextRotation: number, nextCrop: CropBox | null): PageEdits {
    // Rotation/crop change the coordinate space annotations were placed in,
    // so they cannot be carried over. Coordinate-free settings (filter and
    // brightness/contrast adjustments) are kept.
    return {
      rotation: nextRotation,
      crop: nextCrop,
      filter: edits?.filter ?? "none",
      brightness: edits?.brightness ?? 0,
      contrast: edits?.contrast ?? 0,
      strokes: [],
      texts: [],
      blurRegions: [],
    };
  }

  function getCanvasPoint(event: React.PointerEvent<HTMLCanvasElement>): EditPoint | null {
    const canvas = canvasRef.current;
    if (!canvas) {
      return null;
    }
    const rect = canvas.getBoundingClientRect();
    // Use the on-screen rect so coordinates stay correct even when CSS
    // shrinks the canvas below its intrinsic width.
    const displayScaleX = rect.width / Math.max(canvas.width, 1);
    const displayScaleY = rect.height / Math.max(canvas.height, 1);
    const x = (event.clientX - rect.left) / displayScaleX / workingSize.scale;
    const y = (event.clientY - rect.top) / displayScaleY / workingSize.scale;
    const width = canvas.width / workingSize.scale;
    const height = canvas.height / workingSize.scale;
    return {
      x: Math.max(0, Math.min(x, width)),
      y: Math.max(0, Math.min(y, height)),
    };
  }

  function handlePointerDown(event: React.PointerEvent<HTMLCanvasElement>) {
    const point = getCanvasPoint(event);
    if (!point || !edits) {
      return;
    }
    event.currentTarget.setPointerCapture(event.pointerId);
    if (tool === "draw") {
      setActiveStroke({ color: drawColor, width: drawWidth, points: [point], opacity: 1 });
      return;
    }
    if (tool === "highlight") {
      setActiveStroke({
        color: highlightColor,
        width: highlightWidth,
        points: [point],
        opacity: HIGHLIGHT_OPACITY,
      });
      return;
    }
    if (tool === "crop" || tool === "blur") {
      setDragState({ start: point, current: point });
      return;
    }
    if (tool === "text") {
      if (!textValue.trim()) {
        return;
      }
      const nextText: TextAnnotation = {
        text: textValue.trim(),
        x: point.x,
        y: point.y,
        color: textColor,
        fontSize: textSize,
      };
      setEdits((current) =>
        current
          ? {
              ...current,
              texts: [...current.texts, nextText],
            }
          : current,
      );
    }
  }

  function handlePointerMove(event: React.PointerEvent<HTMLCanvasElement>) {
    const point = getCanvasPoint(event);
    if (!point) {
      return;
    }
    if ((tool === "draw" || tool === "highlight") && activeStroke) {
      setActiveStroke((current) =>
        current
          ? {
              ...current,
              points: [...current.points, point],
            }
          : current,
      );
      return;
    }
    if ((tool === "crop" || tool === "blur") && dragState) {
      setDragState({ ...dragState, current: point });
    }
  }

  function handlePointerUp(event: React.PointerEvent<HTMLCanvasElement>) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    if (!edits) {
      return;
    }
    if ((tool === "draw" || tool === "highlight") && activeStroke) {
      if (activeStroke.points.length > 1) {
        setEdits({
          ...edits,
          strokes: [...edits.strokes, activeStroke],
        });
      }
      setActiveStroke(null);
      return;
    }
    if ((tool === "crop" || tool === "blur") && dragState) {
      const region = normalizeRegion(dragState.start, dragState.current);
      if (region.width > 8 && region.height > 8) {
        if (tool === "crop") {
          // The drag happened in the coordinates of the currently cropped
          // view; offset by the existing crop so crops compose correctly.
          const offsetX = edits.crop?.x ?? 0;
          const offsetY = edits.crop?.y ?? 0;
          setEdits(
            transformEdits(edits.rotation, {
              ...region,
              x: region.x + offsetX,
              y: region.y + offsetY,
            }),
          );
        } else {
          const nextRegion: BlurRegion = {
            ...region,
            intensity: blurIntensity,
            mode: regionMode,
            fillColor,
          };
          setEdits({
            ...edits,
            blurRegions: [...edits.blurRegions, nextRegion],
          });
        }
      }
      setDragState(null);
    }
  }

  function handlePointerCancel() {
    setActiveStroke(null);
    setDragState(null);
  }

  async function handleSave() {
    if (!edits) {
      return;
    }
    await onSave(edits);
  }

  async function handleAutoCrop() {
    if (!page || !edits) {
      return;
    }
    setIsAutoCropping(true);
    setAutoCropNote(null);
    try {
      const suggestion = await fetchCropSuggestion(page.jobId, page.id, edits.rotation);
      if (suggestion.crop) {
        setEdits(transformEdits(edits.rotation, suggestion.crop));
        setAutoCropNote("Cropped to the detected document area. Save to apply.");
      } else {
        setAutoCropNote("No document region detected — drag to crop manually.");
      }
    } catch (error) {
      setAutoCropNote(
        error instanceof Error ? error.message : "Auto-crop failed. Try a manual crop.",
      );
    } finally {
      setIsAutoCropping(false);
    }
  }

  return (
    <div className="editor-modal">
      <div className="editor-modal__backdrop" onClick={handleClose} />
      <div className="editor-modal__panel" role="dialog" aria-modal="true" aria-label="Edit page">
        <div className="editor-modal__header">
          <div>
            <h3>Edit {page.previewLabel.toLowerCase()}</h3>
            <p className="muted">
              {activeTool?.hint ?? "Rotate, crop, draw, place text, and blur sensitive areas."}
            </p>
          </div>
          <button
            className="editor-modal__close"
            onClick={handleClose}
            type="button"
            aria-label="Close editor"
          >
            <X size={18} />
          </button>
        </div>

        <div className="editor-modal__body">
          <aside className="editor-sidebar">
            <div className="editor-toolbar editor-toolbar--icons">
              {TOOL_CONFIG.map(({ key, label, Icon }) => (
                <button
                  key={key}
                  className={`secondary-button editor-tool-btn ${tool === key ? "is-active" : ""}`}
                  onClick={() => setTool(key)}
                  title={label}
                  type="button"
                >
                  <Icon size={16} aria-hidden="true" />
                  <span>{label}</span>
                </button>
              ))}
            </div>

            <div className="editor-control-group">
              <span className="editor-group-label">Rotate</span>
              <div className="editor-toolbar">
                <button
                  className="secondary-button"
                  onClick={() => setEdits(transformEdits((edits.rotation + 270) % 360, null))}
                  type="button"
                >
                  <RotateCcw size={14} aria-hidden="true" />
                  Left
                </button>
                <button
                  className="secondary-button"
                  onClick={() => setEdits(transformEdits((edits.rotation + 90) % 360, null))}
                  type="button"
                >
                  <RotateCw size={14} aria-hidden="true" />
                  Right
                </button>
              </div>
              {hasAnnotations ? (
                <p className="editor-note">
                  Rotating or re-cropping clears drawings, text, and blurs.
                </p>
              ) : null}
            </div>

            <div className="editor-control-group">
              <span className="editor-group-label">Cleanup filter</span>
              <div className="editor-toolbar editor-toolbar--icons">
                {(
                  [
                    ["none", "Original"],
                    ["enhance", "Enhance"],
                    ["grayscale", "Grayscale"],
                    ["bw", "B&W"],
                  ] as [PageFilter, string][]
                ).map(([value, label]) => (
                  <button
                    key={value}
                    className={`secondary-button editor-tool-btn ${edits.filter === value ? "is-active" : ""}`}
                    onClick={() => setEdits({ ...edits, filter: value })}
                    type="button"
                  >
                    {label}
                  </button>
                ))}
              </div>
              {edits.filter === "enhance" ? (
                <p className="editor-note">
                  Preview is approximate; the export whitens the background properly.
                </p>
              ) : null}
            </div>

            <div className="editor-control-group">
              <span className="editor-group-label">Adjust</span>
              <label>
                <span>Brightness ({edits.brightness})</span>
                <input
                  type="range"
                  min={-100}
                  max={100}
                  value={edits.brightness}
                  onChange={(event) =>
                    setEdits({ ...edits, brightness: Number(event.target.value) })
                  }
                />
              </label>
              <label>
                <span>Contrast ({edits.contrast})</span>
                <input
                  type="range"
                  min={-100}
                  max={100}
                  value={edits.contrast}
                  onChange={(event) =>
                    setEdits({ ...edits, contrast: Number(event.target.value) })
                  }
                />
              </label>
              {edits.brightness !== 0 || edits.contrast !== 0 ? (
                <button
                  className="secondary-button"
                  onClick={() => setEdits({ ...edits, brightness: 0, contrast: 0 })}
                  type="button"
                >
                  Reset adjustments
                </button>
              ) : null}
            </div>

            {tool === "crop" ? (
              <div className="editor-control-group">
                <span className="editor-group-label">Crop</span>
                <button
                  className="secondary-button"
                  disabled={isAutoCropping || !imageReady}
                  onClick={() => void handleAutoCrop()}
                  type="button"
                >
                  {isAutoCropping ? (
                    <Loader2 size={14} className="spin" aria-hidden="true" />
                  ) : (
                    <Wand2 size={14} aria-hidden="true" />
                  )}
                  Auto-crop to page
                </button>
                {edits.crop ? (
                  <button
                    className="secondary-button"
                    onClick={() => setEdits(transformEdits(edits.rotation, null))}
                    type="button"
                  >
                    Clear crop
                  </button>
                ) : null}
                {autoCropNote ? <p className="editor-note">{autoCropNote}</p> : null}
              </div>
            ) : null}

            {tool === "draw" ? (
              <div className="editor-control-group">
                <label>
                  <span>Stroke color</span>
                  <input
                    type="color"
                    value={drawColor}
                    onChange={(event) => setDrawColor(event.target.value)}
                  />
                </label>
                <label>
                  <span>Stroke width</span>
                  <input
                    type="range"
                    min={2}
                    max={18}
                    value={drawWidth}
                    onChange={(event) => setDrawWidth(Number(event.target.value))}
                  />
                </label>
              </div>
            ) : null}

            {tool === "highlight" ? (
              <div className="editor-control-group">
                <label>
                  <span>Highlight color</span>
                  <input
                    type="color"
                    value={highlightColor}
                    onChange={(event) => setHighlightColor(event.target.value)}
                  />
                </label>
                <label>
                  <span>Marker width</span>
                  <input
                    type="range"
                    min={8}
                    max={36}
                    value={highlightWidth}
                    onChange={(event) => setHighlightWidth(Number(event.target.value))}
                  />
                </label>
              </div>
            ) : null}

            {tool === "text" ? (
              <div className="editor-control-group">
                <label>
                  <span>Text</span>
                  <input value={textValue} onChange={(event) => setTextValue(event.target.value)} />
                </label>
                <label>
                  <span>Color</span>
                  <input
                    type="color"
                    value={textColor}
                    onChange={(event) => setTextColor(event.target.value)}
                  />
                </label>
                <label>
                  <span>Font size</span>
                  <input
                    type="range"
                    min={16}
                    max={56}
                    value={textSize}
                    onChange={(event) => setTextSize(Number(event.target.value))}
                  />
                </label>
              </div>
            ) : null}

            {tool === "blur" ? (
              <div className="editor-control-group">
                <span className="editor-group-label">Hide mode</span>
                <div className="editor-toolbar editor-toolbar--icons">
                  {(
                    [
                      ["blur", "Blur"],
                      ["fill", "Black out"],
                    ] as [RegionMode, string][]
                  ).map(([value, label]) => (
                    <button
                      key={value}
                      className={`secondary-button editor-tool-btn ${
                        regionMode === value ? "is-active" : ""
                      }`}
                      onClick={() => setRegionMode(value)}
                      type="button"
                    >
                      {label}
                    </button>
                  ))}
                </div>
                {regionMode === "blur" ? (
                  <label>
                    <span>Blur strength</span>
                    <input
                      type="range"
                      min={9}
                      max={41}
                      step={2}
                      value={blurIntensity}
                      onChange={(event) => setBlurIntensity(Number(event.target.value))}
                    />
                  </label>
                ) : (
                  <label>
                    <span>Redaction color</span>
                    <input
                      type="color"
                      value={fillColor}
                      onChange={(event) => setFillColor(event.target.value)}
                    />
                  </label>
                )}
              </div>
            ) : null}

            <div className="editor-control-group">
              <span className="editor-group-label">Applied</span>
              <div className="editor-stats">
                <span>Rotation {edits.rotation}°</span>
                <span>
                  {edits.crop ? "Cropped" : "No crop"}
                  {edits.filter !== "none" ? ` · ${edits.filter} filter` : ""}
                  {edits.brightness !== 0 || edits.contrast !== 0 ? " · adjusted" : ""}
                </span>
                <span>
                  {edits.strokes.length} drawing{edits.strokes.length === 1 ? "" : "s"} ·{" "}
                  {edits.texts.length} text · {edits.blurRegions.length} blur
                </span>
              </div>
            </div>

            <div className="editor-toolbar">
              <button
                className="secondary-button"
                disabled={edits.strokes.length === 0}
                onClick={() => setEdits({ ...edits, strokes: edits.strokes.slice(0, -1) })}
                type="button"
              >
                Undo draw
              </button>
              <button
                className="secondary-button"
                disabled={edits.texts.length === 0}
                onClick={() => setEdits({ ...edits, texts: edits.texts.slice(0, -1) })}
                type="button"
              >
                Undo text
              </button>
              <button
                className="secondary-button"
                disabled={edits.blurRegions.length === 0}
                onClick={() =>
                  setEdits({ ...edits, blurRegions: edits.blurRegions.slice(0, -1) })
                }
                type="button"
              >
                Undo blur
              </button>
              <button
                className="secondary-button danger-button"
                onClick={() =>
                  setEdits({
                    rotation: 0,
                    crop: null,
                    filter: "none",
                    brightness: 0,
                    contrast: 0,
                    strokes: [],
                    texts: [],
                    blurRegions: [],
                  })
                }
                type="button"
              >
                Reset all
              </button>
            </div>
          </aside>

          <div className="editor-canvas-wrap">
            {loadError ? (
              <div className="status-banner status-banner--error">
                <strong>Editor unavailable</strong>
                <span>{loadError}</span>
              </div>
            ) : null}
            {!loadError && !imageReady ? (
              <div className="editor-canvas-loading">
                <Loader2 size={22} className="spin" aria-hidden="true" />
                <span>Loading page image…</span>
              </div>
            ) : null}
            <canvas
              className="editor-canvas"
              style={{ cursor: TOOL_CURSOR[tool] }}
              height={workingSize.height}
              ref={canvasRef}
              width={workingSize.width}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerCancel={handlePointerCancel}
            />
          </div>
        </div>

        <div className="editor-modal__footer">
          <button className="secondary-button" onClick={handleClose} type="button">
            Cancel
          </button>
          <button
            className="primary-button"
            disabled={isSaving || !imageReady}
            onClick={() => void handleSave()}
            type="button"
          >
            {isSaving ? (
              <>
                <Loader2 size={16} className="spin" aria-hidden="true" />
                Saving…
              </>
            ) : (
              "Save edits"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

function normalizeRegion(start: EditPoint, end: EditPoint): CropBox {
  const x = Math.round(Math.min(start.x, end.x));
  const y = Math.round(Math.min(start.y, end.y));
  const width = Math.round(Math.abs(end.x - start.x));
  const height = Math.round(Math.abs(end.y - start.y));
  return { x, y, width, height };
}

function renderEditorCanvas({
  canvas,
  image,
  edits,
  scale,
  dragState,
  activeStroke,
  tool,
}: {
  canvas: HTMLCanvasElement;
  image: HTMLImageElement;
  edits: PageEdits;
  scale: number;
  dragState: DragState | null;
  activeStroke: DrawStroke | null;
  tool: EditorTool;
}) {
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    return;
  }

  const previewCanvas = buildPreviewCanvas(image, edits, dragState, activeStroke, tool);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#f3f4f6";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(previewCanvas, 0, 0, previewCanvas.width * scale, previewCanvas.height * scale);
}

function buildPreviewCanvas(
  image: HTMLImageElement,
  edits: PageEdits,
  dragState: DragState | null,
  activeStroke: DrawStroke | null,
  tool: EditorTool,
) {
  const rotatedCanvas = document.createElement("canvas");
  const rotatedCtx = rotatedCanvas.getContext("2d");
  if (!rotatedCtx) {
    return rotatedCanvas;
  }

  const rotation = ((edits.rotation % 360) + 360) % 360;
  const rotatedWidth = rotation % 180 === 0 ? image.naturalWidth : image.naturalHeight;
  const rotatedHeight = rotation % 180 === 0 ? image.naturalHeight : image.naturalWidth;
  rotatedCanvas.width = rotatedWidth;
  rotatedCanvas.height = rotatedHeight;

  rotatedCtx.save();
  if (rotation === 90) {
    rotatedCtx.translate(rotatedWidth, 0);
    rotatedCtx.rotate(Math.PI / 2);
  } else if (rotation === 180) {
    rotatedCtx.translate(rotatedWidth, rotatedHeight);
    rotatedCtx.rotate(Math.PI);
  } else if (rotation === 270) {
    rotatedCtx.translate(0, rotatedHeight);
    rotatedCtx.rotate(-Math.PI / 2);
  }
  rotatedCtx.drawImage(image, 0, 0);
  rotatedCtx.restore();

  const crop = edits.crop ?? { x: 0, y: 0, width: rotatedWidth, height: rotatedHeight };
  const croppedCanvas = document.createElement("canvas");
  const croppedCtx = croppedCanvas.getContext("2d");
  if (!croppedCtx) {
    return rotatedCanvas;
  }
  croppedCanvas.width = crop.width;
  croppedCanvas.height = crop.height;
  croppedCtx.drawImage(
    rotatedCanvas,
    crop.x,
    crop.y,
    crop.width,
    crop.height,
    0,
    0,
    crop.width,
    crop.height,
  );

  applyFilterPreview(
    croppedCtx,
    croppedCanvas.width,
    croppedCanvas.height,
    edits.filter,
    edits.brightness,
    edits.contrast,
  );

  for (const region of edits.blurRegions) {
    if (region.mode === "fill") {
      croppedCtx.save();
      croppedCtx.fillStyle = region.fillColor || "#000000";
      croppedCtx.fillRect(region.x, region.y, region.width, region.height);
      croppedCtx.restore();
      continue;
    }
    const tempCanvas = document.createElement("canvas");
    tempCanvas.width = region.width;
    tempCanvas.height = region.height;
    const tempCtx = tempCanvas.getContext("2d");
    if (!tempCtx) {
      continue;
    }
    tempCtx.drawImage(
      croppedCanvas,
      region.x,
      region.y,
      region.width,
      region.height,
      0,
      0,
      region.width,
      region.height,
    );
    croppedCtx.save();
    croppedCtx.filter = `blur(${Math.max(2, region.intensity / 3)}px)`;
    croppedCtx.drawImage(tempCanvas, region.x, region.y);
    croppedCtx.restore();
  }

  for (const stroke of edits.strokes) {
    drawStroke(croppedCtx, stroke);
  }
  if (activeStroke) {
    drawStroke(croppedCtx, activeStroke);
  }

  for (const text of edits.texts) {
    croppedCtx.fillStyle = text.color;
    croppedCtx.font = `${text.fontSize}px "Segoe UI", sans-serif`;
    croppedCtx.fillText(text.text, text.x, text.y);
  }

  if (dragState && (tool === "crop" || tool === "blur")) {
    const region = normalizeRegion(dragState.start, dragState.current);
    croppedCtx.save();
    if (tool === "crop") {
      // Dim everything outside the pending crop selection.
      croppedCtx.fillStyle = "rgba(15, 23, 42, 0.4)";
      croppedCtx.fillRect(0, 0, croppedCanvas.width, region.y);
      croppedCtx.fillRect(0, region.y, region.x, region.height);
      croppedCtx.fillRect(region.x + region.width, region.y, croppedCanvas.width, region.height);
      croppedCtx.fillRect(0, region.y + region.height, croppedCanvas.width, croppedCanvas.height);
    }
    croppedCtx.strokeStyle = tool === "crop" ? "#0f766e" : "#dc2626";
    croppedCtx.lineWidth = 2;
    croppedCtx.setLineDash([10, 6]);
    croppedCtx.strokeRect(region.x, region.y, region.width, region.height);
    croppedCtx.restore();
  }

  return croppedCanvas;
}

function applyFilterPreview(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  filter: PageFilter,
  brightness: number,
  contrast: number,
) {
  const hasAdjustments = brightness !== 0 || contrast !== 0;
  if ((filter === "none" && !hasAdjustments) || width < 1 || height < 1) {
    return;
  }
  let imageData: ImageData;
  try {
    imageData = ctx.getImageData(0, 0, width, height);
  } catch {
    // Tainted canvas (image served without CORS headers): approximate the
    // look with the built-in canvas filter instead of crashing the preview.
    applyCssFilterFallback(ctx, width, height, filter, brightness, contrast);
    return;
  }
  const data = imageData.data;
  // Same centered brightness/contrast math the backend applies on save.
  const gain = 1 + (contrast / 100) * 0.8;
  const offset = brightness * 0.8;
  for (let i = 0; i < data.length; i += 4) {
    if (hasAdjustments) {
      for (let channel = 0; channel < 3; channel += 1) {
        const adjusted = (data[i + channel] - 128) * gain + 128 + offset;
        data[i + channel] = Math.max(0, Math.min(255, adjusted));
      }
    }
    if (filter === "none") {
      continue;
    }
    const luminance = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
    if (filter === "grayscale") {
      data[i] = data[i + 1] = data[i + 2] = luminance;
    } else if (filter === "bw") {
      const value = luminance > 160 ? 255 : 0;
      data[i] = data[i + 1] = data[i + 2] = value;
    } else {
      // "enhance" approximation: raise contrast and push paper toward white.
      for (let channel = 0; channel < 3; channel += 1) {
        const boosted = (data[i + channel] - 128) * 1.25 + 148;
        data[i + channel] = Math.max(0, Math.min(255, boosted));
      }
    }
  }
  ctx.putImageData(imageData, 0, 0);
}

const CSS_FILTER_FALLBACK: Record<Exclude<PageFilter, "none">, string> = {
  grayscale: "grayscale(1)",
  bw: "grayscale(1) contrast(3) brightness(1.15)",
  enhance: "contrast(1.25) brightness(1.12) saturate(1.05)",
};

function applyCssFilterFallback(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  filter: PageFilter,
  brightness: number,
  contrast: number,
) {
  const copy = document.createElement("canvas");
  copy.width = width;
  copy.height = height;
  const copyCtx = copy.getContext("2d");
  if (!copyCtx) {
    return;
  }
  copyCtx.drawImage(ctx.canvas, 0, 0);
  const parts: string[] = [];
  if (brightness !== 0 || contrast !== 0) {
    parts.push(`brightness(${1 + brightness / 125})`, `contrast(${1 + (contrast / 100) * 0.8})`);
  }
  if (filter !== "none") {
    parts.push(CSS_FILTER_FALLBACK[filter]);
  }
  if (parts.length === 0) {
    return;
  }
  ctx.save();
  ctx.filter = parts.join(" ");
  ctx.clearRect(0, 0, width, height);
  ctx.drawImage(copy, 0, 0);
  ctx.restore();
}

function drawStroke(context: CanvasRenderingContext2D, stroke: DrawStroke) {
  if (stroke.points.length < 2) {
    return;
  }
  context.save();
  context.strokeStyle = stroke.color;
  context.lineWidth = stroke.width;
  context.globalAlpha = stroke.opacity ?? 1;
  context.lineJoin = "round";
  context.lineCap = "round";
  context.beginPath();
  context.moveTo(stroke.points[0].x, stroke.points[0].y);
  for (const point of stroke.points.slice(1)) {
    context.lineTo(point.x, point.y);
  }
  context.stroke();
  context.restore();
}

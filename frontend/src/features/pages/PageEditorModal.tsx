import { useEffect, useMemo, useRef, useState } from "react";
import {
  Crop,
  EyeOff,
  Loader2,
  Pencil,
  RotateCcw,
  RotateCw,
  Type,
} from "lucide-react";
import { resolveArtifactUrl } from "../../lib/api";
import type {
  BlurRegion,
  CropBox,
  DrawStroke,
  EditPoint,
  ExtractedPage,
  PageEdits,
  TextAnnotation,
} from "../../types";

type EditorTool = "crop" | "draw" | "text" | "blur";

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

const TOOL_CONFIG: { key: EditorTool; label: string; Icon: typeof Crop }[] = [
  { key: "crop", label: "Crop", Icon: Crop },
  { key: "draw", label: "Draw", Icon: Pencil },
  { key: "text", label: "Text", Icon: Type },
  { key: "blur", label: "Blur", Icon: EyeOff },
];

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
  const [blurIntensity, setBlurIntensity] = useState(18);
  const [textValue, setTextValue] = useState("Confidential");
  const [textColor, setTextColor] = useState("#111111");
  const [textSize, setTextSize] = useState(28);
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [activeStroke, setActiveStroke] = useState<DrawStroke | null>(null);
  const [imageReady, setImageReady] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

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

    const sourceUrl = resolveArtifactUrl(page.sourceImageUrl ?? page.imageUrl);
    if (!sourceUrl) {
      setLoadError("Source page image is unavailable.");
      return;
    }

    const image = new Image();
    image.onload = () => {
      imageRef.current = image;
      setImageReady(true);
    };
    image.onerror = () => {
      setLoadError("Page image could not be loaded for editing.");
    };
    image.src = sourceUrl;
  }, [page]);

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

  function resetAnnotationsForTransform(nextRotation: number, nextCrop: CropBox | null): PageEdits {
    return {
      rotation: nextRotation,
      crop: nextCrop,
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
    const x = (event.clientX - rect.left) / workingSize.scale;
    const y = (event.clientY - rect.top) / workingSize.scale;
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
    if (tool === "draw") {
      setActiveStroke({ color: drawColor, width: drawWidth, points: [point] });
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
    if (tool === "draw" && activeStroke) {
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

  function handlePointerUp() {
    if (!edits) {
      return;
    }
    if (tool === "draw" && activeStroke) {
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
          setEdits(resetAnnotationsForTransform(edits.rotation, region));
        } else {
          const nextRegion: BlurRegion = { ...region, intensity: blurIntensity };
          setEdits({
            ...edits,
            blurRegions: [...edits.blurRegions, nextRegion],
          });
        }
      }
      setDragState(null);
    }
  }

  async function handleSave() {
    if (!edits) {
      return;
    }
    await onSave(edits);
  }

  return (
    <div className="editor-modal">
      <div className="editor-modal__backdrop" onClick={onClose} />
      <div className="editor-modal__panel" role="dialog" aria-modal="true" aria-label="Edit page">
        <div className="editor-modal__header">
          <div>
            <span className="section-eyebrow">Page editor</span>
            <h3>{page.previewLabel}</h3>
            <p className="muted">
              Rotate, crop, draw, place text, and blur sensitive areas.
            </p>
          </div>
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
              <span className="section-eyebrow">Rotate</span>
              <div className="editor-toolbar">
                <button
                  className="secondary-button"
                  onClick={() =>
                    setEdits(resetAnnotationsForTransform((edits.rotation + 270) % 360, null))
                  }
                  type="button"
                >
                  <RotateCcw size={14} aria-hidden="true" />
                  Left
                </button>
                <button
                  className="secondary-button"
                  onClick={() =>
                    setEdits(resetAnnotationsForTransform((edits.rotation + 90) % 360, null))
                  }
                  type="button"
                >
                  <RotateCw size={14} aria-hidden="true" />
                  Right
                </button>
              </div>
            </div>

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
                <p className="muted">Click on the page to place text.</p>
              </div>
            ) : null}

            {tool === "blur" ? (
              <div className="editor-control-group">
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
                <p className="muted">Drag a rectangle over anything that should be hidden.</p>
              </div>
            ) : null}

            <div className="editor-control-group">
              <span className="section-eyebrow">Current edits</span>
              <div className="editor-stats">
                <span>Rotation {edits.rotation}°</span>
                <span>{edits.crop ? "Crop applied" : "No crop"}</span>
                <span>{edits.strokes.length} strokes</span>
                <span>{edits.texts.length} text items</span>
                <span>{edits.blurRegions.length} blur regions</span>
              </div>
            </div>

            <div className="editor-toolbar">
              <button
                className="secondary-button"
                disabled={edits.strokes.length === 0}
                onClick={() => setEdits({ ...edits, strokes: edits.strokes.slice(0, -1) })}
                type="button"
              >
                Undo stroke
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
                className="secondary-button danger-button"
                onClick={() =>
                  setEdits({ rotation: 0, crop: null, strokes: [], texts: [], blurRegions: [] })
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
            <canvas
              className="editor-canvas"
              height={workingSize.height}
              ref={canvasRef}
              width={workingSize.width}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerLeave={handlePointerUp}
            />
          </div>
        </div>

        <div className="editor-modal__footer">
          <button className="secondary-button" onClick={onClose} type="button">
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

  for (const region of edits.blurRegions) {
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
    croppedCtx.strokeStyle = tool === "crop" ? "#0f766e" : "#dc2626";
    croppedCtx.lineWidth = 2;
    croppedCtx.setLineDash([10, 6]);
    croppedCtx.strokeRect(region.x, region.y, region.width, region.height);
    croppedCtx.restore();
  }

  return croppedCanvas;
}

function drawStroke(context: CanvasRenderingContext2D, stroke: DrawStroke) {
  if (stroke.points.length < 2) {
    return;
  }
  context.save();
  context.strokeStyle = stroke.color;
  context.lineWidth = stroke.width;
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

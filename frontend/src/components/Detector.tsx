import { Ban, Camera, CloudUpload, Eye, ImagePlus, Info, Loader2, RefreshCw, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { ACCEPTED_TYPES, fileFromTransfer, ImageFileError, prepareImage } from "../lib/imageFile";
import { dateTime, pct } from "../lib/format";
import type { PredictResponse } from "../lib/types";
import { btn, ErrorBox, StatusIcon } from "./ui";


function CameraModal({ onCapture, onClose }: { onCapture: (f: File) => void; onClose: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [dark, setDark] = useState(false);

  useEffect(() => {
    let stream: MediaStream | null = null;
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 } }, audio: false })
      .then((s) => {
        stream = s;
        const v = video.current;
        if (v) {
          v.srcObject = s;
          // Webcams send a few black frames while starting: enable Capture only once real frames arrive.
          const onPlaying = () => setTimeout(() => setReady(v.videoWidth > 0), 600);
          v.addEventListener("playing", onPlaying, { once: true });
          v.play().catch(() => undefined);
        }
      })
      .catch((e: Error) =>
        setError(
          e.name === "NotAllowedError"
            ? "Camera permission was denied. Allow camera access in your browser settings, or upload a photo instead."
            : "No camera could be opened on this device. Please upload a photo instead.",
        ),
      );
    return () => stream?.getTracks().forEach((t) => t.stop());
  }, []);

  const capture = () => {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
    ctx.drawImage(v, 0, 0);
    // An all-black frame means the camera delivers no picture: do not send it for classification.
    const px = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    let sum = 0, n = 0;
    for (let i = 0; i < px.length; i += 4 * 97) {
      sum += px[i] + px[i + 1] + px[i + 2];
      n++;
    }
    if (sum / (n * 3) < 12) {
      setDark(true);
      return;
    }
    setDark(false);
    canvas.toBlob((b) => b && onCapture(new File([b], `camera-${Date.now()}.jpg`, { type: "image/jpeg" })), "image/jpeg", 0.92);
  };

  // Portal: an animated ancestor must not trap this fixed-position dialog.
  return createPortal(
    <div className="fixed inset-0 z-50 flex animate-fade-in items-center justify-center bg-forest-950/70 p-4" role="dialog" aria-modal="true" aria-label="Take a photo">
      <div className="w-full max-w-xl rounded-2xl bg-white p-4 shadow-card">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-semibold">Take a photo of the leaf</h3>
          <button onClick={onClose} className="rounded-lg p-1.5 hover:bg-mint-100" aria-label="Close camera">
            <X size={18} />
          </button>
        </div>
        {error ? (
          <ErrorBox message={error} />
        ) : (
          <>
            <video ref={video} playsInline muted className="aspect-[4/3] w-full rounded-xl bg-forest-950 object-cover" />
            {dark ? (
              <p role="alert" className="mt-2 rounded-xl bg-amber-50 p-3 text-xs text-amber-800">
                The camera picture is completely dark, so nothing was captured. Check that the camera is not covered (privacy shutter or
                cover), that no other app is using it, and that there is enough light, then try again. You can also close this and upload
                a photo instead.
              </p>
            ) : (
              <p className="mt-2 text-xs text-slate-500">Place a single leaf in the centre on a plain background, in good light.</p>
            )}
            <button onClick={capture} disabled={!ready} className={`${btn.primary} mt-3 w-full`}>
              {ready ? <Camera size={17} /> : <Loader2 size={17} className="animate-spin" />} {ready ? "Capture photo" : "Starting camera…"}
            </button>
          </>
        )}
      </div>
    </div>,
    document.body,
  );
}

/** Scanner over the preview while the photo is really being analysed (rendered only during the request). */
function Scanner() {
  const corners = ["left-3 top-3 border-l-2 border-t-2 rounded-tl-lg", "right-3 top-3 border-r-2 border-t-2 rounded-tr-lg",
    "bottom-3 left-3 border-b-2 border-l-2 rounded-bl-lg", "bottom-3 right-3 border-b-2 border-r-2 rounded-br-lg"];
  return (
    <div className="pointer-events-none absolute inset-0" role="status" aria-live="polite" data-testid="leaf-scanner">
      <div className="absolute inset-0 bg-forest-950/10" />
      {corners.map((c) => (
        <span key={c} className={`absolute h-8 w-8 border-lime-300 ${c}`} />
      ))}
      <div className="absolute inset-x-0 animate-scan">
        <div className="h-16 -translate-y-1/2 bg-gradient-to-b from-transparent via-lime-300/25 to-transparent" />
        <div className="absolute inset-x-0 top-0 h-0.5 bg-lime-300 shadow-[0_0_12px_3px_rgba(190,220,75,0.75)]" />
      </div>
      <span className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-forest-950/75 px-3 py-1 text-xs font-semibold text-lime-300">
        Analyzing leaf...
      </span>
    </div>
  );
}

/** Shown when the backend's calamansi-leaf check rejects the image: no label, no confidence. */
function InvalidImageCard({ message, reason, onReset }: { message: string; reason?: string; onReset: () => void }) {
  const blurry = !!reason && reason.includes("blurry");
  return (
    <div role="alert" className="space-y-3">
      <div className="flex items-center gap-4 rounded-2xl bg-red-50 p-4 ring-1 ring-red-200">
        <span className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-red-600 text-white">
          <Ban size={24} />
        </span>
        <div className="min-w-0">
          <p className="text-xl font-bold text-red-700">Invalid Image</p>
          <p className="text-sm text-slate-700">{message.replace(/^Invalid Image:\s*/, "")}</p>
          {reason && <p className="mt-1 text-xs text-red-700">Reason: {reason}.</p>}
        </div>
      </div>
      <p className="text-sm text-slate-600">
        The system checks every photo before classifying it and only classifies calamansi leaves. This image was not recognised as one, so it
        was not classified or saved.
      </p>
      {blurry && (
        <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800">
          The photo is too blurry to tell a calamansi leaf from a similar leaf (lemon, lime, orange). Hold the camera steady, tap the
          leaf on the screen to focus, and use good light.
        </p>
      )}
      <ul className="space-y-1 text-xs text-slate-500">
        <li>• Upload a photo where calamansi leaves are clearly visible, not only fruit, another plant, a person or an object.</li>
        <li>• Photos of a calamansi branch or plant are fine if the leaves are large and sharp. Fruit in the photo is not a problem.</li>
        <li>• If it really shows calamansi leaves, move closer so a few leaves fill the frame, in good light.</li>
      </ul>
      <button onClick={onReset} className={btn.primary}>
        <RefreshCw size={16} /> Try Another Photo
      </button>
    </div>
  );
}

export function ResultCard({ result, onReset }: { result: PredictResponse; onReset?: () => void }) {
  const healthy = result.predicted_class === "Healthy";
  return (
    <div className="space-y-3">
      <div className={`flex items-center gap-4 rounded-2xl p-4 ${healthy ? "bg-leaf-50 ring-1 ring-leaf-200" : "bg-amber-50 ring-1 ring-amber-100"}`}>
        <StatusIcon value={result.predicted_class} size={48} />
        <div className="min-w-0">
          <p className={`text-xl font-bold ${healthy ? "text-leaf-700" : "text-amber-700"}`}>{healthy ? "Healthy Leaf" : "Damaged Leaf"}</p>
          <p className="text-sm text-slate-600">
            Confidence: <span className="font-semibold text-forest-950">{pct(result.confidence)}</span>
          </p>
        </div>
      </div>

      <div className="space-y-1.5" aria-label="Class probabilities">
        {(["Healthy", "Damaged"] as const).map((c) => {
          const p = c === "Healthy" ? result.prob_healthy : result.prob_damaged;
          return (
            <div key={c} className="flex items-center gap-3 text-xs">
              <span className="w-16 text-slate-600">{c}</span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-mint-100">
                <div className={`h-full rounded-full ${c === "Healthy" ? "bg-leaf-600" : "bg-amber-500"}`} style={{ width: `${(p ?? 0) * 100}%` }} />
              </div>
              <span className="w-12 text-right font-medium tabular-nums">{pct(p)}</span>
            </div>
          );
        })}
      </div>

      {!healthy && (
        <p className="text-sm text-slate-600">
          The model detected visual patterns it associates with damaged calamansi leaves (such as spots, discoloration or deformation). It
          does not identify a specific disease or cause.
        </p>
      )}
      {result.analysis === "leaf_regions" && (
        <p className="flex gap-2 rounded-xl bg-mint-50 p-3 text-sm text-slate-600">
          <Info size={16} className="mt-0.5 shrink-0 text-leaf-600" />
          The photo shows more than a single leaf, so the system found {result.regions_used} areas with calamansi leaves (out of{" "}
          {result.regions_checked} checked) and combined their results. Fruit and stems were not classified.
        </p>
      )}
      {result.low_confidence && (
        <p className="flex gap-2 rounded-xl bg-amber-50 p-3 text-sm text-amber-700">
          <Info size={16} className="mt-0.5 shrink-0" />
          Low confidence. The photo may be blurry, poorly lit, contain several leaves, or not show a calamansi leaf. Try another photo.
        </p>
      )}
      {result.warning && <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-700">{result.warning}</p>}

      <p className="text-xs text-slate-500">
        Saved {dateTime(result.created_at)} · model {result.model_version}. Confidence is the model's estimate for Healthy vs. Damaged only. It
        says nothing about whether the leaf is calamansi: that is decided beforehand by the separate calamansi-leaf check, which this image
        passed. Both can make mistakes, and neither is a professional plant-health diagnosis.
      </p>

      <div className="flex flex-wrap gap-2">
        {onReset && (
          <button onClick={onReset} className={btn.primary}>
            <RefreshCw size={16} /> Detect Another Leaf
          </button>
        )}
        <Link to={`/app/logs/${result.id}`} className={btn.secondary}>
          <Eye size={16} /> View Details
        </Link>
      </div>
    </div>
  );
}

export default function Detector({ maxMb = 5, openCamera = false }: { maxMb?: number; openCamera?: boolean }) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [invalid, setInvalid] = useState<{ message: string; reason?: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PredictResponse | null>(null);
  const [dragging, setDragging] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [camera, setCamera] = useState(openCamera);
  const input = useRef<HTMLInputElement>(null);
  const pick = useRef(0); // increases with every new selection; stale async work is ignored
  const running = useRef(false); // one classification request at a time
  const cameraSupported = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  const choose = useCallback(
    async (f: File | undefined | null) => {
      if (!f) return;
      const id = ++pick.current;
      setResult(null);
      setInvalid(null);
      setError(null);
      setPreparing(true);
      try {
        const ready = await prepareImage(f, maxMb);
        if (id !== pick.current) return; // a newer photo was chosen meanwhile
        setFile(ready.file);
        setNote(ready.note);
        setPreview(URL.createObjectURL(ready.file));
      } catch (e) {
        if (id !== pick.current) return;
        setError(e instanceof ImageFileError ? e.message : `"${f.name}" could not be read. Please try another photo.`);
      } finally {
        if (id === pick.current) setPreparing(false);
      }
    },
    [maxMb],
  );

  // Dropped or pasted images: a file, or a picture copied/dragged from a web page.
  const fromTransfer = useCallback(
    async (dt: DataTransfer | null, emptyMessage: string | null) => {
      try {
        const f = await fileFromTransfer(dt);
        if (f) await choose(f);
        else if (emptyMessage) setError(emptyMessage);
      } catch (e) {
        setError((e as Error).message);
      }
    },
    [choose],
  );

  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing = target?.closest("input, textarea, [contenteditable=true]");
      const hasImage = [...(e.clipboardData?.items ?? [])].some((i) => i.kind === "file");
      if (typing && !hasImage) return; // normal text paste, e.g. into the search box
      if (!hasImage && !e.clipboardData?.getData("text/html").includes("<img")) return;
      e.preventDefault();
      void fromTransfer(e.clipboardData, null);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [fromTransfer]);

  const reset = () => {
    pick.current++;
    setPreparing(false);
    setFile(null);
    setPreview(null);
    setResult(null);
    setError(null);
    setInvalid(null);
    setNote(null);
    if (input.current) input.current.value = "";
  };

  const run = async () => {
    if (!file || running.current) return;
    running.current = true;
    const id = pick.current;
    setLoading(true);
    setError(null);
    setInvalid(null);
    try {
      const r = await api.predict(file, file.name);
      if (id === pick.current) setResult(r); // ignore a result for a photo that was replaced or removed
    } catch (e) {
      if (id !== pick.current) return;
      if (e instanceof ApiError && e.code === "not_calamansi_leaf") setInvalid({ message: e.message, reason: e.reason });
      else setError((e as Error).message);
    } finally {
      running.current = false;
      setLoading(false);
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    void fromTransfer(e.dataTransfer, "Nothing that can be uploaded was dropped. Drop an image file, or use Choose File.");
  };
  /*
   * Open the Windows/Android file picker - once. The picker closes on the Enter key or on the
   * second click of a double-click, and the rest of that key press or click then lands on this
   * page: on the upload area it used to open the picker again at once, so the dialog seemed stuck.
   * Requests are therefore ignored for 1 s after the picker returns, and a second request from the
   * same gesture (e.g. button + upload area) is ignored too. Time-based only, so it can never lock.
   */
  const picker = useRef({ openedAt: 0, returnedAt: 0 });
  const openPicker = () => {
    const p = picker.current, now = Date.now();
    if (now - p.openedAt < 600 || now - p.returnedAt < 1000) return;
    p.openedAt = now;
    input.current?.click();
  };
  useEffect(() => {
    const el = input.current;
    const returned = () => {
      const p = picker.current;
      if (p.openedAt > p.returnedAt) p.returnedAt = Date.now();
    };
    // "cancel" fires when the picker is closed without a file; focus returns to the window either way.
    el?.addEventListener("cancel", returned);
    window.addEventListener("focus", returned);
    return () => {
      el?.removeEventListener("cancel", returned);
      window.removeEventListener("focus", returned);
    };
  }, []);

  return (
    <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr]">
      {/* ---------- input side ---------- */}
      <div>
        <input
          ref={input}
          type="file"
          accept={[...ACCEPTED_TYPES, "image/*"].join(",")}
          className="hidden"
          onChange={(e) => {
            picker.current.returnedAt = Date.now();
            const f = e.target.files?.[0];
            e.target.value = ""; // so choosing the same file again still triggers a change
            void choose(f);
          }}
          aria-label="Choose leaf image"
        />
        {!preview ? (
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={(e) => {
              if (e.target === e.currentTarget || !(e.target as HTMLElement).closest("button")) openPicker();
            }}
            onKeyDown={(e) => {
              // only keys pressed on the upload area itself; its buttons handle their own keys
              if (e.target === e.currentTarget && !e.repeat && (e.key === "Enter" || e.key === " ")) {
                e.preventDefault();
                openPicker();
              }
            }}
            role="button"
            tabIndex={0}
            aria-label="Choose, drop or paste a leaf image"
            aria-busy={preparing}
            className={`flex min-h-[280px] cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-6 text-center transition focus:outline-none focus-visible:ring-4 focus-visible:ring-leaf-100 ${
              dragging ? "border-leaf-500 bg-leaf-50" : "border-leaf-200 bg-mint-50/60 hover:border-leaf-500/60 hover:bg-mint-50"
            }`}
          >
            {preparing ? (
              <Loader2 size={40} className="animate-spin text-leaf-600" />
            ) : (
              <CloudUpload size={40} className="text-forest-800" strokeWidth={1.6} />
            )}
            <p className="mt-3 font-medium">{preparing ? "Preparing the image…" : "Drag & drop a leaf image here"}</p>
            <p className="my-2 text-xs text-slate-400">or</p>
            <div className="flex flex-wrap justify-center gap-2">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  openPicker();
                }}
                disabled={preparing}
                className={btn.primary}
              >
                <ImagePlus size={16} /> Choose File
              </button>
              {cameraSupported && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setCamera(true);
                  }}
                  disabled={preparing}
                  className={btn.secondary}
                >
                  <Camera size={16} /> Take Photo
                </button>
              )}
            </div>
            <p className="mt-3 text-xs text-slate-500">
              You can also paste a copied image with <kbd className="rounded border border-leaf-200 bg-white px-1 font-sans">Ctrl</kbd>+
              <kbd className="rounded border border-leaf-200 bg-white px-1 font-sans">V</kbd>
            </p>
            <p className="mt-1 text-xs text-slate-500">JPG, PNG or WEBP up to {maxMb} MB · other formats and larger photos are converted automatically</p>
          </div>
        ) : (
          <div className="rounded-2xl border border-leaf-100 bg-mint-50/60 p-3">
            {/* Fixed-size frame: any image size or aspect ratio fits inside, undistorted and uncropped. */}
            <div className="relative h-[260px] w-full overflow-hidden rounded-xl bg-white/60 sm:h-[340px]">
              <img
                src={preview}
                alt="Selected leaf preview"
                className={`h-full w-full object-contain object-center transition-opacity ${preparing ? "opacity-40" : ""}`}
              />
              {loading && <Scanner />}
              {preparing && (
                <div className="absolute inset-0 flex items-center justify-center gap-2 text-sm font-medium text-forest-900" role="status">
                  <Loader2 size={20} className="animate-spin text-leaf-600" /> Preparing the new image…
                </div>
              )}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <div className="mr-auto min-w-0">
                <p className="truncate text-sm text-slate-600" title={file?.name}>
                  {file?.name} · {((file?.size ?? 0) / 1024).toFixed(0)} KB
                </p>
                {note && <p className="text-xs text-leaf-700">{note}</p>}
              </div>
              <button onClick={openPicker} disabled={loading || preparing} className={btn.secondary}>
                <RefreshCw size={15} /> Replace
              </button>
              <button onClick={reset} disabled={loading} className={btn.secondary}>
                <Trash2 size={15} /> Remove
              </button>
            </div>
          </div>
        )}
        <ul className="mt-3 space-y-1 text-xs text-slate-500">
          <li>• Photograph one calamansi leaf, flat, filling a good part of the frame.</li>
          <li>• Use even lighting and a plain background; avoid blur and strong shadows.</li>
        </ul>
      </div>

      {/* ---------- result side ---------- */}
      <div className="flex flex-col rounded-2xl border border-leaf-100 bg-mint-50/40 p-4">
        {error && <ErrorBox message={error} />}
        {invalid ? (
          <InvalidImageCard message={invalid.message} reason={invalid.reason} onReset={() => { reset(); openPicker(); }} />
        ) : result ? (
          <ResultCard result={result} onReset={() => { reset(); openPicker(); }} />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 py-6 text-center">
            {loading ? (
              <>
                <Loader2 size={36} className="animate-spin text-leaf-600" />
                <p className="text-sm text-slate-600">Analyzing leaf… checking that it is a calamansi leaf, then classifying it.</p>
              </>
            ) : (
              <>
                <p className="max-w-xs text-sm text-slate-500">
                  {file ? "Ready. Click Detect to classify this leaf as Healthy or Damaged." : "Select or capture a leaf photo to begin."}
                </p>
                <button onClick={run} disabled={!file || preparing} className={`${btn.primary} w-full max-w-xs`}>
                  Detect Leaf
                </button>
              </>
            )}
          </div>
        )}
      </div>

      {camera && (
        <CameraModal
          onClose={() => setCamera(false)}
          onCapture={(f) => {
            setCamera(false);
            choose(f);
          }}
        />
      )}
    </div>
  );
}

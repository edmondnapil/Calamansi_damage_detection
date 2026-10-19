/**
 * Turns whatever the user picked, dropped or pasted into an upload the API accepts
 * (JPEG, PNG or WEBP within the size limit), without changing what the photo shows.
 *
 *  - The type is read from the file's first bytes, so a real JPEG named .jfif or with
 *    no browser-reported type is accepted.
 *  - Other images the browser can open (AVIF, GIF, BMP, ...) and photos over the size
 *    limit are re-encoded as JPEG, with the long side reduced to MAX_SIDE px at most.
 *    The model works on 224 px inputs, so this does not reduce what it can see.
 */
export const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_SIDE = 2560;

export class ImageFileError extends Error {}

export interface PreparedImage {
  file: File;
  /** e.g. "Converted from AVIF" or "Reduced from 9.4 MB to 1.2 MB"; null when unchanged. */
  note: string | null;
}

async function sniff(file: File): Promise<string | null> {
  const b = new Uint8Array(await file.slice(0, 12).arrayBuffer());
  if (b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return "image/jpeg";
  if (b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47) return "image/png";
  const ascii = (from: number, to: number) => String.fromCharCode(...b.slice(from, to));
  if (ascii(0, 4) === "RIFF" && ascii(8, 12) === "WEBP") return "image/webp";
  return null;
}

const mb = (n: number) => `${(n / 1048576).toFixed(1)} MB`;
const baseName = (name: string) => name.replace(/\.[^.]+$/, "") || "leaf";

async function reencode(file: File, maxBytes: number): Promise<File> {
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    throw new ImageFileError(
      `"${file.name}" could not be opened as an image. Please use a JPG, PNG or WEBP photo` +
        (/\.(heic|heif)$/i.test(file.name) ? " (iPhone HEIC photos: set the camera to \"Most Compatible\" or export as JPG)." : "."),
    );
  }
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#fff"; // transparent PNG/GIF areas become white instead of black
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  for (const quality of [0.92, 0.85, 0.75]) {
    const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, "image/jpeg", quality));
    if (blob && blob.size <= maxBytes) return new File([blob], `${baseName(file.name)}.jpg`, { type: "image/jpeg" });
  }
  throw new ImageFileError(`The image is too large even after reducing it. Please choose a smaller photo.`);
}

export async function prepareImage(file: File, maxMb: number): Promise<PreparedImage> {
  if (file.size === 0) throw new ImageFileError("The selected file is empty.");
  const maxBytes = maxMb * 1024 * 1024;
  const real = await sniff(file);
  if (real && file.size <= maxBytes) {
    // Same bytes; only the declared type is corrected when the browser reported a wrong or empty one.
    return { file: real === file.type ? file : new File([file], file.name, { type: real }), note: null };
  }
  if (!real && file.type && !file.type.startsWith("image/")) {
    throw new ImageFileError(`"${file.name}" is not an image. Please choose a JPG, PNG or WEBP photo.`);
  }
  const out = await reencode(file, maxBytes);
  const note = real ? `Reduced from ${mb(file.size)} to ${mb(out.size)} (limit ${maxMb} MB)` : `Converted to JPG for upload`;
  return { file: out, note };
}

/** First image in a drop or paste. Images dragged from another web page arrive as a link only. */
export async function fileFromTransfer(dt: DataTransfer | null): Promise<File | null> {
  if (!dt) return null;
  const direct = [...(dt.files ?? [])].find((f) => f.type.startsWith("image/") || !f.type) ?? dt.files?.[0];
  if (direct) return direct;
  for (const item of [...(dt.items ?? [])]) {
    if (item.kind === "file") {
      const f = item.getAsFile();
      if (f) return f;
    }
  }
  const html = dt.getData("text/html");
  const url = html.match(/<img[^>]+src=["']([^"']+)["']/i)?.[1] || dt.getData("text/uri-list").split(/\r?\n/).find((l) => l && !l.startsWith("#")) || "";
  if (!url) return null;
  try {
    // Works for data: URLs and for sites that allow it; most websites block it (CORS).
    const res = await fetch(url, { mode: "cors" });
    const blob = await res.blob();
    if (!res.ok || !blob.type.startsWith("image/")) throw new Error();
    const name = url.startsWith("data:") ? "dragged-image" : decodeURIComponent(url.split("/").pop()?.split("?")[0] || "") || "dragged-image";
    return new File([blob], name, { type: blob.type });
  } catch {
    throw new ImageFileError(
      "That image was dragged from a website, which does not allow it to be read directly. Right-click the image and choose \"Copy image\", then press Ctrl+V here, or save it and use Choose File.",
    );
  }
}

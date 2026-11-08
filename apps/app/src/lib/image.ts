/** Photos for Hỏi đáp are shrunk before upload: long side at most 1600 px, JPEG. */

export const MAX_SIDE = 1600;
const SKIP_BELOW_BYTES = 600_000;

export function fitWithin(w: number, h: number, max = MAX_SIDE): { width: number; height: number } {
  const k = Math.min(1, max / Math.max(w, h));
  return { width: Math.max(1, Math.round(w * k)), height: Math.max(1, Math.round(h * k)) };
}

/**
 * Smaller JPEG of an image file. A file the browser cannot decode (HEIC on most desktops) is returned unchanged,
 * the server reads it itself; a small image is also left alone.
 */
export async function downscaleImage(file: Blob, max = MAX_SIDE, quality = 0.85): Promise<Blob> {
  if (typeof createImageBitmap !== "function") return file;
  let bmp: ImageBitmap;
  try {
    bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    return file;
  }
  try {
    const { width, height } = fitWithin(bmp.width, bmp.height, max);
    if (width === bmp.width && file.size < SKIP_BELOW_BYTES && file.type === "image/jpeg") return file;
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.drawImage(bmp, 0, 0, width, height);
    const out = await new Promise<Blob | null>((r) => canvas.toBlob(r, "image/jpeg", quality));
    if (!out) return file;
    return out.size < file.size || file.type !== "image/jpeg" ? out : file;
  } finally {
    bmp.close();
  }
}

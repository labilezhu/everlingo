// ref: docs/ADR/20260816-markdown-image.md — 决策 8
// 前端「必要时」canvas 缩放：超过 maxPixels 时等比缩到限内并重新编码为原 MIME。
// src_resource_sha256 在调用本模块之前（scale 前）已由原始字节算出；缩放失败回退原图，
// 由后端 preprocess_image 兜底保证 ≤1920x1200。

export const DEFAULT_MAX_PIXELS = 1920 * 1200;

export function shouldScale(width: number, height: number, maxPixels: number = DEFAULT_MAX_PIXELS): boolean {
  return width * height > maxPixels;
}

function scaleCanvas(
  bmp: ImageBitmap,
  targetWidth: number,
  targetHeight: number,
  mimeType: string,
): Promise<Blob | null> {
  return new Promise((resolve) => {
    try {
      const canvas = document.createElement('canvas');
      canvas.width = targetWidth;
      canvas.height = targetHeight;
      const ctx = canvas.getContext('2d');
      if (!ctx) return resolve(null);
      ctx.drawImage(bmp, 0, 0, targetWidth, targetHeight);
      canvas.toBlob((blob) => resolve(blob), mimeType);
    } catch {
      resolve(null);
    }
  });
}

/** 需要缩放时返回缩放后的 Blob；原图在限内或缩放失败返回 null（调用方上传原图）。 */
export async function scaleImageIfNeeded(
  file: File,
  maxPixels: number = DEFAULT_MAX_PIXELS,
): Promise<Blob | null> {
  if (typeof createImageBitmap !== 'function') return null;
  let bmp: ImageBitmap;
  try {
    bmp = await createImageBitmap(file);
  } catch {
    return null;
  }
  try {
    const { width, height } = bmp;
    if (!shouldScale(width, height, maxPixels)) return null;
    const scale = Math.sqrt(maxPixels / (width * height));
    const targetWidth = Math.max(1, Math.round(width * scale));
    const targetHeight = Math.max(1, Math.round(height * scale));
    return await scaleCanvas(bmp, targetWidth, targetHeight, file.type);
  } finally {
    bmp.close();
  }
}

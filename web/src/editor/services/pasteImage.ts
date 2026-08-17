// ref: docs/impl-spec/vault-editor.md §图片插入（粘贴图片）
// 从剪贴板 DataTransfer 取出首个图片文件。只接受后端允许的 MIME（与 <input accept> 对齐），
// 避免上传到后端 415。不支持的类型（如 gif）返回 null，让默认文本粘贴照常。

const ALLOWED_MIME = new Set(['image/jpeg', 'image/png', 'image/webp']);

export function extractImageFile(dt: DataTransfer | null): File | null {
  if (!dt || !dt.items) return null;
  const items = dt.items;
  for (let i = 0; i < items.length; i++) {
    const it = items[i];
    if (it.kind === 'file' && it.type.startsWith('image/') && ALLOWED_MIME.has(it.type)) {
      const f = it.getAsFile();
      if (f) return f;
    }
  }
  return null;
}
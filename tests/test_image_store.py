"""
图片存储单元测试：ImageStore

ref: docs/ADR/20260812-image-chat.md §14「存储位置」
物理落盘 {workspace}/sessions/{session_id}/images/{sha256}.{ext}
Phase 2 引入 Pillow 预处理：EXIF 方向校正 → strip metadata → 超 1920x1200 按比例缩放，
saved_resource_sha256 为处理后字节的 hash。
"""
import hashlib
from io import BytesIO

import pytest
from PIL import Image, ImageOps

from everlingo.image.image_store import ImageStore, MAX_PIXELS, sha256_of_bytes
from everlingo.workspace import init_workspace_dir


@pytest.fixture
def store(tmp_path):
    """每个测试独立的 ImageStore + 临时 workspace。"""
    init_workspace_dir(tmp_path)
    yield ImageStore()
    init_workspace_dir(None)  # 复位全局 workspace，避免污染其它测试


def _make_png_bytes(size=(64, 48), color=(200, 30, 30)) -> bytes:
    """生成真实 PNG 字节。"""
    img = Image.new("RGB", size, color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_jpeg_bytes(size=(64, 48), color=(30, 30, 200)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_exif_rotated_jpeg_bytes(size=(64, 48)) -> bytes:
    """生成带 EXIF orientation=6（旋转 90°）的 JPEG。"""
    img = Image.new("RGB", size, (10, 200, 10))
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation
    buf = BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


class TestImageStoreSave:
    def test_save_stores_bytes_and_returns_asset(self, store, tmp_path):
        data = _make_png_bytes()
        src_sha = sha256_of_bytes(data)
        asset = store.save("sess-1", src_sha, data, "image/png")

        assert asset.src_resource_sha256 == src_sha
        assert asset.mime_type == "image/png"
        assert asset.width == 64
        assert asset.height == 48
        # 物理文件存在（Phase 2 处理后的字节落盘，saved_sha 可能变化但不为空）
        assert asset.saved_resource_sha256
        file_path = tmp_path / "sessions" / "sess-1" / "images" / f"{asset.saved_resource_sha256}.png"
        assert file_path.exists()
        assert file_path.read_bytes() == store.read_bytes(src_sha)

    def test_get_returns_saved_asset(self, store):
        data = _make_png_bytes()
        src_sha = sha256_of_bytes(data)
        store.save("sess-1", src_sha, data, "image/png")
        asset = store.get(src_sha)
        assert asset is not None
        assert asset.src_resource_sha256 == src_sha

    def test_get_returns_none_for_unknown(self, store):
        assert store.get("nonexistent") is None

    def test_unsupported_mime_raises(self, store):
        data = _make_png_bytes()
        with pytest.raises(ValueError, match="unsupported mime type"):
            store.save("sess-1", sha256_of_bytes(data), data, "image/gif")

    def test_sha_mismatch_raises(self, store):
        data = _make_png_bytes()
        with pytest.raises(ValueError, match="sha256 mismatch"):
            store.save("sess-1", "wrong-sha", data, "image/png")

    def test_invalid_image_data_raises(self, store):
        data = b"\x89PNG\r\n\x1a\n" + b"fake-png-content"
        with pytest.raises(ValueError, match="invalid image data"):
            store.save("sess-1", sha256_of_bytes(data), data, "image/png")

    def test_duplicate_upload_is_idempotent(self, store, tmp_path):
        data = _make_png_bytes()
        src_sha = sha256_of_bytes(data)
        a1 = store.save("sess-1", src_sha, data, "image/png")
        a2 = store.save("sess-1", src_sha, data, "image/png")

        assert a1.src_resource_sha256 == a2.src_resource_sha256
        # 同 sha256 返回同一注册项
        assert store.get(src_sha) is a1


class TestImageStorePreprocess:
    def test_large_image_is_rescaled(self, store):
        """超过 1920x1200 像素按比例缩放（ADR §14 / §32）。"""
        data = _make_png_bytes(size=(2000, 1600))
        src_sha = sha256_of_bytes(data)
        asset = store.save("sess-1", src_sha, data, "image/png")

        assert asset.width * asset.height <= MAX_PIXELS
        assert asset.width <= asset.height * (2000 / 1600) + 1  # 保持比例

    def test_small_image_not_scaled(self, store):
        data = _make_png_bytes(size=(64, 48))
        src_sha = sha256_of_bytes(data)
        asset = store.save("sess-1", src_sha, data, "image/png")
        assert (asset.width, asset.height) == (64, 48)
        assert asset.saved_resource_sha256 == src_sha  # 无需处理时 saved == src

    def test_exif_orientation_applied(self, store, tmp_path):
        """带 EXIF orientation=6 的 JPEG 校正为横向后存储。"""
        data = _make_exif_rotated_jpeg_bytes(size=(64, 48))
        src_sha = sha256_of_bytes(data)
        asset = store.save("sess-1", src_sha, data, "image/jpeg")

        # orientation=6 将 (64,48) 旋转为 (48,64)
        assert (asset.width, asset.height) == (48, 64)
        saved = store.read_bytes(src_sha)
        saved_img = Image.open(BytesIO(saved))
        assert saved_img.size == (48, 64)
        # strip metadata：重新读回的图不含 EXIF
        assert "exif" not in saved_img.info


class TestImageStoreReadBytes:
    def test_read_bytes_returns_stored_bytes(self, store):
        data = _make_png_bytes()
        src_sha = sha256_of_bytes(data)
        store.save("sess-1", src_sha, data, "image/png")
        bytes_read = store.read_bytes(src_sha)
        assert bytes_read is not None
        re_loaded = Image.open(BytesIO(bytes_read))
        assert re_loaded.format == "PNG"

    def test_read_bytes_returns_none_for_unknown(self, store):
        assert store.read_bytes("unknown") is None


class TestSha256OfBytes:
    def test_returns_hex(self):
        expected = hashlib.sha256(b"abc").hexdigest()
        assert sha256_of_bytes(b"abc") == expected
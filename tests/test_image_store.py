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
from PIL.PngImagePlugin import PngInfo

from everlingo.image.image_store import (
    ImageStore,
    MAX_PIXELS,
    save_vault_image,
    sha256_of_bytes,
    slugify,
    sniff_image_mime,
)
from everlingo.workspace import init_workspace_dir, lang_vault_dir


@pytest.fixture
def store(tmp_path):
    """每个测试独立的 ImageStore + 临时 workspace。"""
    init_workspace_dir(tmp_path)
    yield ImageStore()
    init_workspace_dir(None)  # 复位全局 workspace，避免污染其它测试


@pytest.fixture
def ws(tmp_path):
    """临时 workspace，仅复位全局状态。"""
    init_workspace_dir(tmp_path)
    yield tmp_path
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


def _add_png_self_metadata(data: bytes, src_sha: str) -> bytes:
    """模拟 save_vault_image 对 PNG 追加 tEXt 自有元数据后的落盘字节。"""
    img = Image.open(BytesIO(data))
    info = PngInfo()
    info.add_text("src_resource_sha256", src_sha)
    buf = BytesIO()
    img.save(buf, format="PNG", pnginfo=info)
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


class TestSaveVaultImage:
    """save_vault_image：vault 图片存储（无状态、按路径幂等）。

    ref: docs/ADR/20260816-markdown-image.md — 决策 5
    写盘到 lang_vault_dir(lang).resolve() / vault_rel_path；
    storage_key = memory://languages/{lang}/vault/{vault_rel_path}。
    """

    def _rel(self, src_sha: str, ext: str = ".png") -> str:
        return f"items/vocab/hello-kitty.assets/{src_sha}{ext}"

    def test_saves_bytes_and_returns_asset(self, ws):
        data = _make_png_bytes(size=(64, 48))
        src_sha = sha256_of_bytes(data)
        rel = self._rel(src_sha)
        asset = save_vault_image("en", rel, data, "image/png")

        assert asset.src_resource_sha256 == src_sha
        assert asset.mime_type == "image/png"
        assert (asset.width, asset.height) == (64, 48)
        assert asset.storage_key == f"memory://languages/en/vault/{rel}"
        # 小图无需缩放/校正：saved 应为落盘字节（注入 tEXt 后）的 hash
        file_path = lang_vault_dir("en") / rel
        assert file_path.is_file()
        assert sha256_of_bytes(file_path.read_bytes()) == asset.saved_resource_sha256
        assert file_path.read_bytes() == _add_png_self_metadata(data, src_sha)

    def test_creates_parent_dirs(self, ws):
        data = _make_png_bytes()
        src_sha = sha256_of_bytes(data)
        rel = self._rel(src_sha)
        save_vault_image("en", rel, data, "image/png")
        assert (lang_vault_dir("en") / rel).is_file()

    def test_large_image_is_rescaled(self, ws):
        data = _make_png_bytes(size=(2000, 1600))
        src_sha = sha256_of_bytes(data)
        asset = save_vault_image("en", self._rel(src_sha), data, "image/png")
        assert asset.width * asset.height <= MAX_PIXELS
        assert asset.width <= asset.height * (2000 / 1600) + 1  # 保持比例

    def test_exif_orientation_applied(self, ws):
        data = _make_exif_rotated_jpeg_bytes(size=(64, 48))
        src_sha = sha256_of_bytes(data)
        asset = save_vault_image("en", self._rel(src_sha, ".jpg"), data, "image/jpeg")
        assert (asset.width, asset.height) == (48, 64)

    def test_unsupported_mime_raises(self, ws):
        data = _make_png_bytes()
        with pytest.raises(ValueError, match="unsupported mime type"):
            save_vault_image("en", self._rel(sha256_of_bytes(data)), data, "image/gif")

    def test_path_escape_raises(self, ws):
        data = _make_png_bytes()
        src_sha = sha256_of_bytes(data)
        with pytest.raises(ValueError, match="path escape"):
            save_vault_image("en", f"../../outside/{src_sha}.png", data, "image/png")

    def test_invalid_lang_raises(self, ws):
        data = _make_png_bytes()
        src_sha = sha256_of_bytes(data)
        with pytest.raises(ValueError, match="invalid lang name"):
            save_vault_image("../..", self._rel(src_sha), data, "image/png")

    def test_sha_mismatch_raises(self, ws):
        """末段 stem 非 64 位 hex（非合法 src_resource_sha256）→ 400。"""
        data = _make_png_bytes()
        with pytest.raises(ValueError, match="sha256 mismatch"):
            save_vault_image("en", self._rel("wrong-sha"), data, "image/png")

    def test_scaled_bytes_under_original_sha_accepted(self, ws):
        """前端 scale 场景：上传「已缩放」字节，但文件名 stem 是 scale 前原始字节的 sha。

        服务端信任 stem 作为 src_resource_sha256（格式校验），不再对收到的字节重算比对。
        """
        original = _make_png_bytes(size=(2000, 1600))
        src_sha = sha256_of_bytes(original)
        scaled = _make_png_bytes(size=(640, 480), color=(1, 2, 3))
        rel = self._rel(src_sha)

        asset = save_vault_image("en", rel, scaled, "image/png")

        assert asset.src_resource_sha256 == src_sha
        # 落盘为「收到的字节」预处理后的结果，而非原始字节
        file_path = lang_vault_dir("en") / rel
        assert file_path.is_file()
        assert sha256_of_bytes(file_path.read_bytes()) == asset.saved_resource_sha256
        assert file_path.read_bytes() != original

    def test_invalid_image_data_raises(self, ws):
        data = b"\x89PNG\r\n\x1a\n" + b"fake-png-content"
        with pytest.raises(ValueError, match="invalid image data"):
            save_vault_image("en", self._rel(sha256_of_bytes(data)), data, "image/png")

    def test_idempotent_same_path(self, ws):
        data = _make_png_bytes()
        src_sha = sha256_of_bytes(data)
        rel = self._rel(src_sha)
        a1 = save_vault_image("en", rel, data, "image/png")
        a2 = save_vault_image("en", rel, data, "image/png")

        assert a1.src_resource_sha256 == a2.src_resource_sha256
        assert a1.saved_resource_sha256 == a2.saved_resource_sha256
        assert a1.storage_key == a2.storage_key
        # 幂等：不重复写盘（文件时间戳不变）
        file_path = lang_vault_dir("en") / rel
        mtime = file_path.stat().st_mtime_ns
        save_vault_image("en", rel, data, "image/png")
        assert file_path.stat().st_mtime_ns == mtime

    def test_jpeg_self_metadata_exif(self, ws):
        data = _make_jpeg_bytes(size=(64, 48))
        src_sha = sha256_of_bytes(data)
        save_vault_image("en", self._rel(src_sha, ".jpg"), data, "image/jpeg")
        file_path = lang_vault_dir("en") / self._rel(src_sha, ".jpg")
        img = Image.open(file_path)
        exif = img.getexif()
        assert exif.get(0x9286) == f"src_resource_sha256={src_sha}"

    def test_png_self_metadata_text(self, ws):
        data = _make_png_bytes(size=(64, 48))
        src_sha = sha256_of_bytes(data)
        save_vault_image("en", self._rel(src_sha), data, "image/png")
        file_path = lang_vault_dir("en") / self._rel(src_sha)
        img = Image.open(file_path)
        assert img.text.get("src_resource_sha256") == src_sha

    def test_explicit_src_sha_with_slug_stem(self, ws):
        """显式传 src_resource_sha256：stem 可为英文 slug（跳过 stem 64-hex 校验）。

        ref: docs/ADR/20260817-save-image-from-chat-to-note.md — 决策 2
        """
        data = _make_png_bytes(size=(64, 48))
        src_sha = sha256_of_bytes(data)
        rel = "items/vocab/hello-kitty.assets/english-exercise-2cf24dba.png"
        asset = save_vault_image(
            "en", rel, data, "image/png", src_resource_sha256=src_sha
        )

        assert asset.src_resource_sha256 == src_sha
        assert asset.mime_type == "image/png"
        assert asset.storage_key == f"memory://languages/en/vault/{rel}"
        file_path = lang_vault_dir("en") / rel
        assert file_path.is_file()
        # tEXt 自有元数据用显式传入的 src_sha
        img = Image.open(file_path)
        assert img.text.get("src_resource_sha256") == src_sha

    def test_explicit_src_sha_invalid_value_raises(self, ws):
        """显式传的 src_resource_sha256 本身非 64 位 hex → 400（防元数据注入）。"""
        data = _make_png_bytes()
        with pytest.raises(ValueError, match="sha256 mismatch"):
            save_vault_image(
                "en",
                "items/vocab/hello-kitty.assets/english-exercise.png",
                data,
                "image/png",
                src_resource_sha256="not-a-sha",
            )


class TestSlugify:
    """slugify：自由文本 → 英文 slug。

    ref: docs/ADR/20260817-save-image-from-chat-to-note.md — 决策 1
    """

    def test_basic(self):
        assert slugify("English Exercise") == "english-exercise"

    def test_non_ascii_replaced(self):
        assert slugify("中文错题 image") == "image"

    def test_collapse_dashes(self):
        assert slugify("a  b--c__d") == "a-b-c-d"

    def test_strip_edges(self):
        assert slugify("  --hello--  ") == "hello"

    def test_truncate(self):
        assert len(slugify("x" * 100)) == 40

    def test_truncate_does_not_end_with_dash(self):
        s = slugify("x" * 39 + "-y" * 10)
        assert s.endswith("x")
        assert len(s) <= 40

    def test_empty_falls_back(self):
        assert slugify("") == "image"
        assert slugify("!!!") == "image"


class TestSniffImageMime:
    """sniff_image_mime：从原始字节嗅探 MIME。

    ref: docs/ADR/20260818-image-chat-wechat.md — 决策 4
    Wechat 下载字节不带 MIME/扩展名，靠 Pillow 读 format 映射。
    """

    def test_png(self):
        assert sniff_image_mime(_make_png_bytes()) == "image/png"

    def test_jpeg(self):
        assert sniff_image_mime(_make_jpeg_bytes()) == "image/jpeg"

    def test_webp(self):
        buf = BytesIO()
        Image.new("RGB", (8, 8), (1, 2, 3)).save(buf, format="WEBP")
        assert sniff_image_mime(buf.getvalue()) == "image/webp"

    def test_corrupt_bytes_returns_none(self):
        assert sniff_image_mime(b"not an image at all") is None

    def test_empty_bytes_returns_none(self):
        assert sniff_image_mime(b"") is None
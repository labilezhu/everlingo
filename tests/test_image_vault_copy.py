"""
copy_session_image_to_vault 工具单元测试：make_copy_session_image_tool

ref: docs/ADR/20260817-save-image-from-chat-to-note.md — 决策 3 / 决策 4
验证：
- 把 session 图片复制到 {mdname}.assets/ 并返回 markdown 相对路径
- md 在 vault 根目录（无目录段）时的路径计算
- 图片字节不可取（进程重启模拟）→ 返回 ok=false 不抛异常
- 同 src_sha + 同 slug_hint 幂等（不重复写盘）
- slug_hint 为空/非 ASCII → 回退 "image"
"""
import json
from io import BytesIO

import pytest
from PIL import Image

from everlingo.image.image_store import ImageStore, sha256_of_bytes
from everlingo.tools.image_vault_copy import make_copy_session_image_tool
from everlingo.workspace import init_workspace_dir, lang_vault_dir


def _make_png_bytes(size=(64, 48), color=(200, 30, 30)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def store(tmp_path):
    """每个测试独立的 ImageStore + 临时 workspace。"""
    init_workspace_dir(tmp_path)
    yield ImageStore()
    init_workspace_dir(None)


def _make_tool(store):
    return make_copy_session_image_tool(store, "en")


def _register_png(store, size=(64, 48), color=(200, 30, 30)) -> str:
    data = _make_png_bytes(size=size, color=color)
    src_sha = sha256_of_bytes(data)
    store.save("sess-1", src_sha, data, "image/png")
    return src_sha


class TestCopySessionImageToVault:
    @pytest.mark.asyncio
    async def test_copies_image_and_returns_relative_path(self, store):
        src_sha = _register_png(store)
        tool = _make_tool(store)

        out = json.loads(await tool.ainvoke({
            "src_resource_sha256": src_sha,
            "md_file_path": "items/vocab/english-exercise--01JZABD123.md",
            "slug_hint": "English Exercise",
        }))

        stem = f"english-exercise-{src_sha[:8]}"
        assert out["ok"] is True
        assert out["mime_type"] == "image/png"
        assert out["markdown_relative_path"] == (
            f"english-exercise--01JZABD123.assets/{stem}.png"
        )
        assert out["vault_rel_path"] == (
            f"items/vocab/english-exercise--01JZABD123.assets/{stem}.png"
        )
        file_path = lang_vault_dir("en") / out["vault_rel_path"]
        assert file_path.is_file()
        # tEXt 自有元数据含完整 src_sha（溯源）
        img = Image.open(file_path)
        assert img.text.get("src_resource_sha256") == src_sha

    @pytest.mark.asyncio
    async def test_root_md_file_uses_flat_assets_dir(self, store):
        src_sha = _register_png(store)
        tool = _make_tool(store)

        out = json.loads(await tool.ainvoke({
            "src_resource_sha256": src_sha,
            "md_file_path": "index.md",
            "slug_hint": "Hello World",
        }))

        assert out["ok"] is True
        expected = f"index.assets/hello-world-{src_sha[:8]}.png"
        assert out["vault_rel_path"] == expected
        assert out["markdown_relative_path"] == expected
        assert (lang_vault_dir("en") / expected).is_file()

    @pytest.mark.asyncio
    async def test_missing_bytes_returns_error(self, store):
        tool = _make_tool(store)

        out = json.loads(await tool.ainvoke({
            "src_resource_sha256": "0" * 64,
            "md_file_path": "items/vocab/x.md",
            "slug_hint": "whatever",
        }))

        assert out["ok"] is False
        assert "unavailable" in out["error"]

    @pytest.mark.asyncio
    async def test_idempotent_same_sha_and_hint(self, store):
        src_sha = _register_png(store)
        tool = _make_tool(store)
        args = {
            "src_resource_sha256": src_sha,
            "md_file_path": "items/vocab/x.md",
            "slug_hint": "Quiz",
        }

        r1 = json.loads(await tool.ainvoke(args))
        r2 = json.loads(await tool.ainvoke(args))
        assert r1["ok"] is True
        assert r1["vault_rel_path"] == r2["vault_rel_path"]
        file_path = lang_vault_dir("en") / r1["vault_rel_path"]
        mtime = file_path.stat().st_mtime_ns
        await tool.ainvoke(args)
        assert file_path.stat().st_mtime_ns == mtime

    @pytest.mark.asyncio
    async def test_empty_slug_hint_falls_back(self, store):
        src_sha = _register_png(store)
        tool = _make_tool(store)

        out = json.loads(await tool.ainvoke({
            "src_resource_sha256": src_sha,
            "md_file_path": "items/vocab/x.md",
            "slug_hint": "!!!",
        }))

        assert out["ok"] is True
        assert out["vault_rel_path"] == f"items/vocab/x.assets/image-{src_sha[:8]}.png"

    @pytest.mark.asyncio
    async def test_jpeg_image_copies(self, store):
        from PIL import Image as PILImage

        img = PILImage.new("RGB", (64, 48), (30, 30, 200))
        buf = BytesIO()
        img.save(buf, format="JPEG")
        data = buf.getvalue()
        src_sha = sha256_of_bytes(data)
        store.save("sess-1", src_sha, data, "image/jpeg")
        tool = _make_tool(store)

        out = json.loads(await tool.ainvoke({
            "src_resource_sha256": src_sha,
            "md_file_path": "items/vocab/x.md",
            "slug_hint": "wrong-answer",
        }))

        assert out["ok"] is True
        assert out["mime_type"] == "image/jpeg"
        assert out["markdown_relative_path"] == (
            f"x.assets/wrong-answer-{src_sha[:8]}.jpg"
        )
        img2 = Image.open(lang_vault_dir("en") / out["vault_rel_path"])
        exif = img2.getexif()
        assert exif.get(0x9286) == f"src_resource_sha256={src_sha}"

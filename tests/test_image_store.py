"""
图片存储单元测试：ImageStore

ref: docs/ADR/20260812-image-chat.md §14「存储位置」
物理落盘 {workspace}/sessions/{session_id}/images/{sha256}.{ext}
"""
import hashlib

import pytest

from everlingo.image.image_store import ImageStore, sha256_of_bytes
from everlingo.workspace import init_workspace_dir


@pytest.fixture
def store(tmp_path):
    """每个测试独立的 ImageStore + 临时 workspace。"""
    init_workspace_dir(tmp_path)
    yield ImageStore()
    init_workspace_dir(None)  # 复位全局 workspace，避免污染其它测试


def _bytes(data: bytes) -> bytes:
    return data


class TestImageStoreSave:
    def test_save_stores_bytes_and_returns_asset(self, store, tmp_path):
        data = b"\x89PNG\r\n\x1a\n" + b"fake-png-content"
        src_sha = sha256_of_bytes(data)
        asset = store.save("sess-1", src_sha, data, "image/png")

        assert asset.src_resource_sha256 == src_sha
        assert asset.saved_resource_sha256 == src_sha  # Phase 1 不处理，saved == src
        assert asset.mime_type == "image/png"
        assert asset.size == len(data)
        assert asset.storage_key == f"session://sess-1/{src_sha}"

        # 物理文件存在
        file_path = tmp_path / "sessions" / "sess-1" / "images" / f"{src_sha}.png"
        assert file_path.exists()
        assert file_path.read_bytes() == data

    def test_get_returns_saved_asset(self, store):
        data = b"hello-image-bytes"
        src_sha = sha256_of_bytes(data)
        store.save("sess-1", src_sha, data, "image/png")
        asset = store.get(src_sha)
        assert asset is not None
        assert asset.src_resource_sha256 == src_sha

    def test_get_returns_none_for_unknown(self, store):
        assert store.get("nonexistent") is None

    def test_unsupported_mime_raises(self, store):
        data = b"x"
        with pytest.raises(ValueError, match="unsupported mime type"):
            store.save("sess-1", sha256_of_bytes(data), data, "image/gif")

    def test_sha_mismatch_raises(self, store):
        data = b"real-content"
        with pytest.raises(ValueError, match="sha256 mismatch"):
            store.save("sess-1", "wrong-sha", data, "image/png")

    def test_duplicate_upload_is_idempotent(self, store, tmp_path):
        data = b"same-content"
        src_sha = sha256_of_bytes(data)
        a1 = store.save("sess-1", src_sha, data, "image/png")
        a2 = store.save("sess-1", src_sha, data, "image/png")

        assert a1.src_resource_sha256 == a2.src_resource_sha256
        # 同 sha256 返回同一注册项
        assert store.get(src_sha) is a1
        # 只写一次文件
        file_path = tmp_path / "sessions" / "sess-1" / "images" / f"{src_sha}.png"
        assert file_path.exists()

    def test_sessions_are_isolated(self, store):
        data = b"content"
        src_sha = sha256_of_bytes(data)
        store.save("sess-a", src_sha, data, "image/png")
        assert store.get(src_sha) is not None


class TestSha256OfBytes:
    def test_returns_hex(self):
        expected = hashlib.sha256(b"abc").hexdigest()
        assert sha256_of_bytes(b"abc") == expected

"""WS-Master 容器生命周期测试：状态机、并发控制、探活。

mock docker SDK + httpx 以快速验证状态流转。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from everlingo.ws_master.config import MasterConfig
from everlingo.ws_master.db import get_conn
from everlingo.ws_master.lifecycle import ContainerLifecycle
from everlingo.ws_master.repo import UserRepo, WsContainerRepo


@pytest.fixture
def config(tmp_path: Path) -> MasterConfig:
    return MasterConfig(
        listen="0.0.0.0:8101",
        shared_secret="test-secret",
        db=str(tmp_path / "test.db"),
        host_ws_dir=str(tmp_path / "workspaces"),
        image="test-image:latest",
        network="test-net",
        ws_template=str(tmp_path / "template.yaml"),
        openai_api_key="test-key",
        openai_base_url="https://test.api",
        openai_model="test-model",
        openai_embedding_model="test-embed",
        idle_timeout=1200,
        healthcheck_interval=60,
        readiness_timeout=5,  # short for tests
        max_ws_per_user=1,
    )


@pytest.fixture
def db_repos(config: MasterConfig, tmp_path: Path):
    """Create repos with a fresh DB. Connection stays open for test duration."""
    conn = get_conn(config.db)
    user_repo = UserRepo(conn)
    ws_repo = WsContainerRepo(conn)
    yield conn, user_repo, ws_repo
    conn.close()


@pytest.fixture
def user_and_ws(db_repos):
    """Create a user and a default ws-container."""
    conn, user_repo, ws_repo = db_repos
    user = user_repo.add("mark", "Mark", "hash")
    ws = ws_repo.add(
        user_id=user.user_id,
        container_name="everlingo-mark-a1b2c3d4",
        host_workspace_dir="/tmp/ws/mark/a1b2c3d4",
        is_default=True,
    )
    return user, ws


# ---------------------------------------------------------------------------
# Mock docker client
# ---------------------------------------------------------------------------


def _mock_docker_client(container_ip: str = "172.18.0.3") -> MagicMock:
    """Create a mock docker client with a mock container."""
    client = MagicMock()
    mock_container = MagicMock()
    mock_container.id = "docker-id-123"
    type(mock_container).status = PropertyMock(return_value="running")
    mock_container.attrs = {
        "NetworkSettings": {
            "Networks": {
                "test-net": {"IPAddress": container_ip},
            },
        },
    }
    client.containers.create.return_value = mock_container
    client.containers.get.return_value = mock_container
    return client


# ---------------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_started_absent_to_started(config, db_repos, user_and_ws):
    """absent → create → start → probe → started"""
    conn, user_repo, ws_repo = db_repos
    user, ws = user_and_ws

    mock_docker = _mock_docker_client()
    lc = ContainerLifecycle(config, ws_repo, user_repo, docker_client=mock_docker)

    # Mock probe to succeed
    lc._probe = AsyncMock(return_value=True)  # type: ignore

    url, status = await lc.ensure_started(ws.ws_container_id)
    assert status == "started"
    assert url == "http://172.18.0.3:8000"
    assert mock_docker.containers.create.called

    create_kwargs = mock_docker.containers.create.call_args.kwargs
    nc = create_kwargs["networking_config"]
    assert ws.container_name in nc[config.network]["Aliases"]
    assert "network_aliases" not in create_kwargs

    # Verify DB status
    updated = ws_repo.get_by_id(ws.ws_container_id)
    assert updated.status == "started"
    assert updated.docker_container_id == "docker-id-123"
    conn.close()


@pytest.mark.asyncio
async def test_ensure_started_stopped_to_started(config, db_repos, user_and_ws):
    """stopped → start → probe → started"""
    conn, user_repo, ws_repo = db_repos
    user, ws = user_and_ws

    # Set to stopped
    ws_repo.update_status(ws.ws_container_id, "stopped", docker_container_id="docker-old")

    mock_docker = _mock_docker_client()
    lc = ContainerLifecycle(config, ws_repo, user_repo, docker_client=mock_docker)
    lc._probe = AsyncMock(return_value=True)  # type: ignore

    url, status = await lc.ensure_started(ws.ws_container_id)
    assert status == "started"
    assert "docker-old" not in url

    # Should not create, only get + start
    assert mock_docker.containers.get.called
    conn.close()


@pytest.mark.asyncio
async def test_ensure_started_already_started(config, db_repos, user_and_ws):
    """started + healthy → return URL immediately"""
    conn, user_repo, ws_repo = db_repos
    user, ws = user_and_ws

    ws_repo.update_status(ws.ws_container_id, "started", docker_container_id="docker-abc")

    mock_docker = _mock_docker_client()
    lc = ContainerLifecycle(config, ws_repo, user_repo, docker_client=mock_docker)
    lc._probe = AsyncMock(return_value=True)  # type: ignore

    url, status = await lc.ensure_started(ws.ws_container_id)
    assert status == "started"
    conn.close()


@pytest.mark.asyncio
async def test_ensure_started_probe_timeout(config, db_repos, user_and_ws):
    """probe timeout → error"""
    conn, user_repo, ws_repo = db_repos
    user, ws = user_and_ws

    mock_docker = _mock_docker_client()
    lc = ContainerLifecycle(config, ws_repo, user_repo, docker_client=mock_docker)
    lc._probe = AsyncMock(return_value=False)  # type: ignore

    url, status = await lc.ensure_started(ws.ws_container_id)
    assert status == "error"
    assert url is None

    updated = ws_repo.get_by_id(ws.ws_container_id)
    assert updated.status == "error"
    conn.close()


@pytest.mark.asyncio
async def test_ensure_started_concurrent_in_flight(config, db_repos, user_and_ws):
    """并发请求同一 ws 复用 in-flight 结果。"""
    conn, user_repo, ws_repo = db_repos
    user, ws = user_and_ws

    mock_docker = _mock_docker_client()
    lc = ContainerLifecycle(config, ws_repo, user_repo, docker_client=mock_docker)

    # Use a slow probe that returns after a delay
    async def slow_probe(_url: str) -> bool:
        await asyncio.sleep(0.1)
        return True

    lc._probe = slow_probe  # type: ignore

    # Fire two concurrent requests
    async def start():
        return await lc.ensure_started(ws.ws_container_id)

    results = await asyncio.gather(start(), start())
    # Both should return started
    for url, status in results:
        assert status == "started"
    # Create should only be called once
    assert mock_docker.containers.create.call_count == 1
    conn.close()


@pytest.mark.asyncio
async def test_stop(config, db_repos, user_and_ws):
    """stop stops docker container and updates status."""
    conn, user_repo, ws_repo = db_repos
    user, ws = user_and_ws

    ws_repo.update_status(ws.ws_container_id, "started", docker_container_id="docker-abc")

    mock_docker = _mock_docker_client()
    lc = ContainerLifecycle(config, ws_repo, user_repo, docker_client=mock_docker)

    result = await lc.stop(ws.ws_container_id)
    assert result is True
    assert mock_docker.containers.get.called

    updated = ws_repo.get_by_id(ws.ws_container_id)
    assert updated.status == "stopped"
    conn.close()


@pytest.mark.asyncio
async def test_remove(config, db_repos, user_and_ws):
    """remove stops and removes docker container + deletes row."""
    conn, user_repo, ws_repo = db_repos
    user, ws = user_and_ws

    ws_repo.update_status(ws.ws_container_id, "started", docker_container_id="docker-abc")

    mock_docker = _mock_docker_client()
    lc = ContainerLifecycle(config, ws_repo, user_repo, docker_client=mock_docker)

    result = await lc.remove(ws.ws_container_id)
    assert result is True

    assert ws_repo.get_by_id(ws.ws_container_id) is None
    conn.close()


@pytest.mark.asyncio
async def test_reconcile_started_gone(config, db_repos, user_and_ws):
    """启动对账：started 但容器不存在的 → absent。"""
    conn, user_repo, ws_repo = db_repos
    user, ws = user_and_ws

    ws_repo.update_status(ws.ws_container_id, "started", docker_container_id="docker-gone")

    mock_docker = _mock_docker_client()
    mock_docker.containers.get.side_effect = __import__("docker").errors.NotFound("gone")
    lc = ContainerLifecycle(config, ws_repo, user_repo, docker_client=mock_docker)

    await lc.reconcile()

    updated = ws_repo.get_by_id(ws.ws_container_id)
    assert updated.status == "absent"
    conn.close()


@pytest.mark.asyncio
async def test_reconcile_started_running(config, db_repos, user_and_ws):
    """启动对账：started + 容器运行 + 探活成功 → 保持 started。"""
    conn, user_repo, ws_repo = db_repos
    user, ws = user_and_ws

    ws_repo.update_status(ws.ws_container_id, "started", docker_container_id="docker-abc")

    mock_docker = _mock_docker_client()
    lc = ContainerLifecycle(config, ws_repo, user_repo, docker_client=mock_docker)
    lc._probe = AsyncMock(return_value=True)  # type: ignore

    await lc.reconcile()

    updated = ws_repo.get_by_id(ws.ws_container_id)
    assert updated.status == "started"
    conn.close()


@pytest.mark.asyncio
async def test_create_injects_public_base_url_env(config, db_repos, user_and_ws):
    """创建 ws-container 时把 MasterConfig.public_base_url 注入为
    EVERLINGO_PUBLIC_BASE_URL env。

    ws-container 内 setting.get_web_public_base_url() 据此 env fallback 返回外部域名，
    Chat Agent 据此生成指向外部域名的笔记链接（Web Chatbot / Chrome Extension 依赖）。
    ref: docs/impl-spec/multiple-users/ws-master.md — public_base_url 透传
    """
    conn, user_repo, ws_repo = db_repos
    user, ws = user_and_ws

    # 设一个非默认 public_base_url
    config.public_base_url = "https://app.everlingo.com"

    mock_docker = _mock_docker_client()
    lc = ContainerLifecycle(config, ws_repo, user_repo, docker_client=mock_docker)
    lc._probe = AsyncMock(return_value=True)  # type: ignore

    await lc.ensure_started(ws.ws_container_id)

    create_kwargs = mock_docker.containers.create.call_args.kwargs
    env = create_kwargs["environment"]
    assert env["EVERLINGO_PUBLIC_BASE_URL"] == "https://app.everlingo.com"

    nc = create_kwargs["networking_config"]
    assert ws.container_name in nc[config.network]["Aliases"]
    assert "network_aliases" not in create_kwargs
    conn.close()
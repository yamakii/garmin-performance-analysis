"""Integration tests for the WorkerClient + shim reload architecture.

These exercise the real ``WorkerClient`` (spawning ``python -m garmin_mcp.worker``
subprocesses) and the shim handlers in ``garmin_mcp.server``. The worker reads a
copied verification DB via ``GARMIN_DATA_DIR`` so ``call``/``info`` operations hit
real data without touching production.

Key guarantees under test:

- ``WorkerClient.rpc`` round-trips a real ``call`` to the registry.
- ``restart()`` swaps in a fresh process that imports the latest on-disk code.
- A worker crash is survived: the next ``rpc`` respawns and the client lives on.
- ``reload_server`` keeps the *shim* process alive (no ``os._exit``) and emits a
  ``tools/list_changed`` notification.
"""

from __future__ import annotations

import json
import os
import shutil
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

import garmin_mcp.server as server
from garmin_mcp.worker_client import WorkerClient

# Activity id present in the generated verification DB.
FIXTURE_ACTIVITY_ID = 12345678901


def _point_env_at_db(data_dir: Path, db_src: Path) -> None:
    """Copy the verification DB into ``data_dir`` and set ``GARMIN_DATA_DIR``.

    Worker subprocesses inherit ``os.environ``; pointing it here makes every
    spawned worker read the isolated copy rather than production data.
    """
    db_dir = data_dir / "database"
    db_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_src, db_dir / "garmin_performance.duckdb")
    os.environ["GARMIN_DATA_DIR"] = str(data_dir)


@pytest.fixture
def worker_env(
    verification_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point ``GARMIN_DATA_DIR`` at an isolated verification DB copy."""
    data_dir = tmp_path / "wdata"
    monkeypatch.setenv("GARMIN_DATA_DIR", str(data_dir))
    _point_env_at_db(data_dir, verification_db_path)
    return data_dir


# --------------------------------------------------------------------------- #
# WorkerClient
# --------------------------------------------------------------------------- #


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rpc_roundtrip(worker_env: Path) -> None:
    """start() then a real ``call`` round-trips to ok=True with data."""
    client = WorkerClient()
    try:
        await client.start()
        resp = await client.rpc(
            "call",
            "get_date_by_activity_id",
            {"activity_id": FIXTURE_ACTIVITY_ID},
        )
    finally:
        await client.aclose()

    assert resp["ok"] is True, f"call failed: {resp.get('error')}"
    assert resp["data"] is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_restart_picks_up_new_code(
    worker_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """restart() spawns a fresh process that sees an edited on-disk module.

    A throwaway ``sentinel`` module is imported by a custom worker-equivalent
    module; mutating it between restarts and re-reading proves the *same*
    WorkerClient picks up new code without reconnecting.
    """
    pkg_dir = tmp_path / "fresh_pkg"
    pkg_dir.mkdir()
    sentinel = pkg_dir / "sentinel.py"
    # A tiny worker-like module that answers one "call" with sentinel.VALUE.
    probe = pkg_dir / "probe_worker.py"
    probe.write_text(textwrap.dedent("""
        import json, sys
        import sentinel
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            req = json.loads(line)
            resp = {"id": req.get("id"), "ok": True, "data": sentinel.VALUE}
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
        """))

    monkeypatch.setenv(
        "PYTHONPATH",
        os.pathsep.join([str(pkg_dir), os.environ.get("PYTHONPATH", "")]),
    )

    def write_sentinel(value: int) -> None:
        sentinel.write_text(f"VALUE = {value}\n")
        cache = pkg_dir / "__pycache__"
        if cache.exists():
            shutil.rmtree(cache)

    client = WorkerClient(module="probe_worker")
    try:
        write_sentinel(111)
        await client.start()
        first = await client.rpc("call", "x", {})
        assert first["data"] == 111

        # Edit on-disk code, restart the SAME client: new value, no reconnect.
        write_sentinel(222)
        await client.restart()
        second = await client.rpc("call", "x", {})
        assert second["data"] == 222
    finally:
        await client.aclose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rpc_after_worker_crash_recovers(worker_env: Path) -> None:
    """An externally-killed worker is respawned on the next rpc; client lives."""
    client = WorkerClient()
    try:
        await client.start()
        # Kill the worker out from under the client.
        assert client._proc is not None
        client._proc.kill()
        await client._proc.wait()

        # Next rpc must not raise: it respawns and returns a valid response.
        resp = await client.rpc(
            "call",
            "get_date_by_activity_id",
            {"activity_id": FIXTURE_ACTIVITY_ID},
        )
        assert resp["ok"] is True, f"recovery call failed: {resp.get('error')}"
        assert resp["data"] is not None
    finally:
        await client.aclose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rpc_large_payload_over_default_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A response line larger than asyncio's 64 KiB default round-trips intact.

    Proves ``start()`` raises the StreamReader limit: a probe worker echoing a
    ~300 KB payload (well past the 64 KiB default that used to overrun
    ``readline()``) is read back whole via a single ``rpc``.
    """
    pkg_dir = tmp_path / "big_pkg"
    pkg_dir.mkdir()
    probe = pkg_dir / "probe_worker.py"
    probe.write_text(textwrap.dedent("""
        import json, sys
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            req = json.loads(line)
            resp = {"id": req.get("id"), "ok": True, "data": "x" * 300_000}
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
        """))

    monkeypatch.setenv(
        "PYTHONPATH",
        os.pathsep.join([str(pkg_dir), os.environ.get("PYTHONPATH", "")]),
    )

    client = WorkerClient(module="probe_worker")
    try:
        await client.start()
        resp = await client.rpc("call", "x", {})
    finally:
        await client.aclose()

    assert resp["ok"] is True, f"large payload failed: {resp.get('error')}"
    assert len(resp["data"]) == 300_000


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rpc_oversized_line_returns_error_and_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An overrun past the stream limit degrades to one clean error, then recovers.

    With ``_STREAM_LIMIT`` monkeypatched down to 1 KiB, a probe worker that first
    replies with a ~10 KB line overruns ``readline()`` (``LimitOverrunError`` ->
    ``ValueError``): ``rpc`` must return ``ok=False`` with a non-empty error and
    respawn. A following ``rpc`` whose reply is small (< 1 KiB) must succeed,
    proving the pipe was not left desynchronized.
    """
    import garmin_mcp.worker_client as worker_client

    monkeypatch.setattr(worker_client, "_STREAM_LIMIT", 1024)

    pkg_dir = tmp_path / "overrun_pkg"
    pkg_dir.mkdir()
    # File-based flag so the "serve oversized once" decision survives the respawn
    # (a fresh worker process would otherwise reset any in-memory state).
    flag = pkg_dir / "served.flag"
    probe = pkg_dir / "probe_worker.py"
    probe.write_text(textwrap.dedent(f"""
        import json, os, sys
        flag = {str(flag)!r}
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            req = json.loads(line)
            if not os.path.exists(flag):
                # First reply across all workers: oversized (~10 KB) line.
                open(flag, "w").close()
                data = "x" * 10_000
            else:
                data = "ok"
            resp = {{"id": req.get("id"), "ok": True, "data": data}}
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
        """))

    monkeypatch.setenv(
        "PYTHONPATH",
        os.pathsep.join([str(pkg_dir), os.environ.get("PYTHONPATH", "")]),
    )

    client = WorkerClient(module="probe_worker")
    try:
        await client.start()
        first = await client.rpc("call", "x", {})
        assert first["ok"] is False
        assert first["error"]

        # Respawned worker: its first reply is small and must round-trip.
        second = await client.rpc("call", "x", {})
        assert second["ok"] is True, f"recovery call failed: {second.get('error')}"
        assert second["data"] == "ok"
    finally:
        await client.aclose()


# --------------------------------------------------------------------------- #
# shim (server.py)
# --------------------------------------------------------------------------- #


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_tools_includes_worker_and_server_tools(worker_env: Path) -> None:
    """list_tools returns worker domain tools plus the 2 server tools."""
    client = WorkerClient()
    try:
        with patch.object(server, "worker", client):
            tools = await server.list_tools()
    finally:
        await client.aclose()

    names = {t.name for t in tools}
    assert "get_server_info" in names
    assert "reload_server" in names
    # A representative domain tool sourced from the worker schema.
    assert "get_performance_trends" in names

    # Total count == worker domain tools + 2 server tools, with no overlap.
    domain = [t for t in tools if t.name not in {"get_server_info", "reload_server"}]
    assert len(tools) == len(domain) + 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reload_keeps_shim_process_alive(worker_env: Path) -> None:
    """reload_server restarts only the worker; shim PID unchanged + notify sent."""
    client = WorkerClient()
    shim_pid = os.getpid()
    mock_session = AsyncMock()
    fake_ctx = type("Ctx", (), {"session": mock_session})()

    try:
        await client.start()
        with (
            patch.object(server, "worker", client),
            patch.object(
                type(server.mcp),
                "request_context",
                property(lambda self: fake_ctx),
            ),
        ):
            old_worker_pid = client._proc.pid  # type: ignore[union-attr]
            result = await server._handle_reload_server()
            new_worker_pid = client._proc.pid  # type: ignore[union-attr]
    finally:
        await client.aclose()

    # Shim process is unchanged.
    assert os.getpid() == shim_pid
    # Worker was actually swapped for a fresh process.
    assert new_worker_pid != old_worker_pid
    # tools/list_changed was emitted.
    mock_session.send_tool_list_changed.assert_awaited_once()

    data = json.loads(result[0].text)
    assert data["success"] is True
    assert data["list_changed_sent"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_call_after_reload_serves_new_code(worker_env: Path) -> None:
    """After reload_server, a subsequent call is served by the fresh worker.

    E2E promotion of the PoC: reload swaps the worker, then a real ``call`` via
    the shim returns a valid result from the new process (same shim session).
    """
    client = WorkerClient()
    fake_ctx = type("Ctx", (), {"session": AsyncMock()})()
    try:
        await client.start()
        with (
            patch.object(server, "worker", client),
            patch.object(
                type(server.mcp),
                "request_context",
                property(lambda self: fake_ctx),
            ),
        ):
            await server._handle_reload_server()
            result = await server._dispatch_tool(
                "get_date_by_activity_id",
                {"activity_id": FIXTURE_ACTIVITY_ID},
            )
    finally:
        await client.aclose()

    data = json.loads(result[0].text)
    assert "error" not in data
    assert data is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_server_info_merges_shim_and_worker(worker_env: Path) -> None:
    """get_server_info merges shim started_at with worker table_count."""
    client = WorkerClient()
    try:
        await client.start()
        with patch.object(server, "worker", client):
            result = await server._handle_get_server_info()
    finally:
        await client.aclose()

    data = json.loads(result[0].text)
    # Shim-level field.
    assert isinstance(data["started_at"], str)
    assert data["ready"] is True
    # Worker-level field.
    assert isinstance(data["table_count"], int)
    assert data["table_count"] > 0

"""Lifecycle manager for the swappable execution worker.

The MCP shim (``server.py``) holds exactly one :class:`WorkerClient`. The client
owns a ``python -m garmin_mcp.worker`` subprocess and speaks newline-delimited
JSON over its stdin/stdout (see :mod:`garmin_mcp.worker` for the contract). The
shim itself stays a tiny, *unchanging* process that keeps the MCP session alive;
all volatile domain code lives in the worker, so swapping the worker process
(``restart``) is what makes a code change live without dropping the session.

Concurrency: a single ``asyncio.Lock`` serializes each request/response
round-trip with the worker. Reads dominate the workload so the throughput cost
is negligible; a future version may pool workers if write contention appears.

Crash recovery: if the worker dies mid-flight (readline returns EOF), the
current ``rpc`` triggers a respawn and returns an ``{"ok": false, "error": ...}``
response. The shim process itself never dies, so the MCP session survives a
worker crash.
"""

from __future__ import annotations

import asyncio
import json
import sys
from itertools import count
from typing import Any


class WorkerClient:
    """Owns and talks to a single fresh-process worker over JSON-line IPC.

    Args:
        python: Python interpreter used to spawn the worker. Defaults to the
            shim's own interpreter so the worker shares the same venv.
        module: Worker module run with ``-m``. Defaults to
            ``garmin_mcp.worker``.
    """

    def __init__(
        self, python: str | None = None, module: str = "garmin_mcp.worker"
    ) -> None:
        self._python = python or sys.executable
        self._module = module
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._ids = count(1)

    async def start(self) -> None:
        """Spawn the worker subprocess if it is not already running."""
        if self._proc is not None and self._proc.returncode is None:
            return
        self._proc = await asyncio.create_subprocess_exec(
            self._python,
            "-m",
            self._module,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )

    async def rpc(
        self, op: str, tool: str = "", args: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send one request to the worker and return its parsed response.

        Serialized via the internal lock so concurrent callers never interleave
        their writes/reads on the shared pipe. If the worker has died (or dies
        mid-call), it is respawned and the call returns an ``ok=False`` error
        rather than propagating an exception that could take down the shim.

        Args:
            op: One of ``"schema"``, ``"call"``, ``"info"``.
            tool: Tool name (only meaningful for ``op="call"``).
            args: Tool arguments (only meaningful for ``op="call"``).

        Returns:
            ``{"ok": True, "data": ...}`` on success or
            ``{"ok": False, "error": str}`` on failure.
        """
        async with self._lock:
            req = {"id": next(self._ids), "op": op, "tool": tool, "args": args or {}}
            try:
                return await self._roundtrip(req)
            except (BrokenPipeError, ConnectionResetError) as e:
                # Pipe died before/while writing: respawn and report the error.
                await self._respawn()
                return {"ok": False, "error": repr(e)}

    async def _roundtrip(self, req: dict[str, Any]) -> dict[str, Any]:
        """Write one request line and read one response line.

        Raises:
            BrokenPipeError/ConnectionResetError: propagated to ``rpc`` for
                respawn handling.
        """
        await self.start()
        assert self._proc is not None
        assert self._proc.stdin is not None
        assert self._proc.stdout is not None

        line = (json.dumps(req, default=str) + "\n").encode()
        self._proc.stdin.write(line)
        await self._proc.stdin.drain()

        raw = await self._proc.stdout.readline()
        if not raw:
            # EOF: the worker crashed mid-call. Respawn so the *next* rpc works,
            # and report this call as an error.
            await self._respawn()
            return {"ok": False, "error": "worker crashed (EOF on stdout)"}
        resp: dict[str, Any] = json.loads(raw.decode())
        return resp

    async def restart(self) -> None:
        """Terminate the current worker and warm-respawn a fresh one.

        Used by ``reload_server``: a new worker imports the latest on-disk code,
        so the swap makes signature-compatible changes live. Respawning eagerly
        (rather than lazily on the next call) avoids making the first post-reload
        call pay the startup cost.
        """
        async with self._lock:
            await self._respawn()

    async def _respawn(self) -> None:
        """Terminate any existing worker, then start a fresh one.

        Caller must hold ``self._lock``.
        """
        await self._terminate()
        await self.start()

    async def _terminate(self) -> None:
        """Best-effort terminate the current worker process.

        Caller must hold ``self._lock``.
        """
        proc = self._proc
        self._proc = None
        if proc is None or proc.returncode is not None:
            return
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except TimeoutError:
            proc.kill()
            await proc.wait()

    async def aclose(self) -> None:
        """Terminate the worker and release resources."""
        async with self._lock:
            await self._terminate()

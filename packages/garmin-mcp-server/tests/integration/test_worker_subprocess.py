"""Integration tests for the worker as a spawned subprocess.

These spawn a real ``python -m garmin_mcp.worker`` process, speak the
newline-delimited JSON IPC, and assert the fresh-process semantics that make the
worker the hot-reload foundation.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

FIXTURE_ACTIVITY_ID = 12345678901


def _worker_env(data_dir: Path, db_src: Path) -> dict[str, str]:
    """Build a subprocess env pointing the worker at a copied verification DB.

    The worker resolves its DB via ``GARMIN_DATA_DIR/database/...``; we copy the
    template DB into that layout so the spawned process reads real data.
    """
    db_dir = data_dir / "database"
    db_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_src, db_dir / "garmin_performance.duckdb")

    env = os.environ.copy()
    env["GARMIN_DATA_DIR"] = str(data_dir)
    return env


@pytest.mark.integration
def test_worker_subprocess_roundtrip(
    verification_db_path: Path, tmp_path: Path
) -> None:
    """A spawned worker answers one ``call`` request with one parseable JSON line."""
    env = _worker_env(tmp_path / "wdata", verification_db_path)

    proc = subprocess.Popen(
        [sys.executable, "-m", "garmin_mcp.worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        request = json.dumps(
            {
                "id": 42,
                "op": "call",
                "tool": "get_date_by_activity_id",
                "args": {"activity_id": FIXTURE_ACTIVITY_ID},
            }
        )
        stdout, stderr = proc.communicate(request + "\n", timeout=60)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=10)

    lines = [line for line in stdout.splitlines() if line.strip()]
    assert lines, f"worker produced no output; stderr={stderr}"

    resp = json.loads(lines[0])  # must be valid JSON
    assert resp["id"] == 42
    assert resp["ok"] is True, f"call failed: {resp.get('error')}"
    assert resp["data"] is not None


@pytest.mark.integration
def test_worker_fresh_process_reflects_disk_code(tmp_path: Path) -> None:
    """Each spawn imports fresh on-disk code, so edits between spawns take effect.

    This is the hot-reload PoC: the worker is a stateless fresh process, so a
    swapped/edited module is reflected on the next spawn. We isolate the proof to
    a throwaway module imported by a tiny harness (same Python invocation the
    worker uses) and mutate it between two spawns.
    """
    pkg_dir = tmp_path / "fresh_pkg"
    pkg_dir.mkdir()
    module_path = pkg_dir / "sentinel.py"

    harness = textwrap.dedent("""
        import sentinel
        print(sentinel.VALUE)
        """)

    def spawn_and_read(value: int) -> str:
        module_path.write_text(f"VALUE = {value}\n")
        # Drop any cached bytecode so the fresh process recompiles from the
        # current on-disk source (sub-second edits share an mtime-second, which
        # would otherwise let a stale .pyc win).
        cache_dir = pkg_dir / "__pycache__"
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join([str(pkg_dir), env.get("PYTHONPATH", "")])
        result = subprocess.run(
            [sys.executable, "-c", harness],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    first = spawn_and_read(111)
    assert first == "111"

    # Mutate the on-disk module, then re-spawn: a fresh process must see new code.
    second = spawn_and_read(222)
    assert second == "222"
    assert first != second

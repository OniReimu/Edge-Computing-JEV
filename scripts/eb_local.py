#!/usr/bin/env python3
"""CLI manager for Edgebench self-hosted local model servers.

Commands:
  scripts/eb_local.py start <semif|laya|qwen_json>
  scripts/eb_local.py stop <semif|laya|qwen_json>
  scripts/eb_local.py status [semif|laya|qwen_json]

Manages exactly one server at a time, strictly refusing to start a second concurrent server.
Writes metadata (pid, port, model, backend) to runs/_local/<name>.json.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any

# Ensure repository root is on sys.path
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

VENV_PYTHON = Path(sys.executable)  # the environment this manager runs in
LOCAL_RUNS_DIR = _repo_root / "runs" / "_local"

SERVER_CONFIGS = {
    "semif": {
        "script": "scripts/eb_serve_semif.py",
        "port": 8601,
        "default_args": ["--backend", "mlx", "--mode", "shared"],
    },
    "laya": {
        "script": "scripts/eb_serve_laya.py",
        "port": 8602,
        "default_args": ["--device", "mps"],
    },
    "qwen_json": {
        "script": "scripts/eb_serve_qwen_json.py",
        "port": 8603,
        "default_args": [],
    },
}


def is_pid_alive(pid: int) -> bool:
    """Check if process with given PID is still running."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def get_active_server() -> tuple[str | None, dict[str, Any] | None]:
    """Check if any server metadata file exists and process is alive."""
    if not LOCAL_RUNS_DIR.exists():
        return None, None

    for f in LOCAL_RUNS_DIR.glob("*.json"):
        name = f.stem
        try:
            with open(f, "r", encoding="utf-8") as stream:
                data = json.load(stream)
            pid = int(data.get("pid", 0))
            if is_pid_alive(pid):
                return name, data
            else:
                # Stale file cleanup
                try:
                    f.unlink()
                except OSError:
                    pass
        except Exception:
            pass

    return None, None


def query_health(port: int, timeout_s: float = 3.0) -> dict[str, Any] | None:
    """Query GET http://127.0.0.1:<port>/health."""
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port=port, timeout=timeout_s)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        if resp.status == 200:
            raw = resp.read().decode("utf-8")
            conn.close()
            return json.loads(raw)
        conn.close()
    except Exception:
        pass
    return None


def cmd_start(name: str, extra_args: list[str]) -> int:
    if name not in SERVER_CONFIGS:
        print(f"Error: Unknown server '{name}'. Must be one of: {list(SERVER_CONFIGS.keys())}")
        return 1

    active_name, active_data = get_active_server()
    if active_name is not None and active_data is not None:
        print(
            f"Error: Server '{active_name}' is already running with PID {active_data.get('pid')} "
            f"on port {active_data.get('port')}. Refusing to start a second local server."
        )
        return 1

    cfg = SERVER_CONFIGS[name]
    port = cfg["port"]
    script_path = _repo_root / cfg["script"]

    LOCAL_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOCAL_RUNS_DIR / f"{name}.log"
    meta_file = LOCAL_RUNS_DIR / f"{name}.json"

    # Command line args
    cmd = [
        str(VENV_PYTHON),
        str(script_path),
        "--port",
        str(port),
    ] + cfg["default_args"] + extra_args

    print(f"Starting '{name}' server on port {port}...")
    log_stream = open(log_file, "w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(_repo_root),
        stdout=log_stream,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
    )

    # Wait for server to become healthy (up to 180s for model loading & 5 warmup calls)
    print(f"Waiting for '{name}' to load weights, complete 5 warmup calls, and report healthy...")
    max_wait_s = 180
    start_t = time.time()
    health_info = None

    while time.time() - start_t < max_wait_s:
        if not is_pid_alive(proc.pid):
            log_stream.close()
            with open(log_file, "r", encoding="utf-8") as f:
                logs = f.read()
            print(f"Error: Server '{name}' exited prematurely (PID {proc.pid}). Logs:\n{logs}")
            return 1

        health_info = query_health(port, timeout_s=1.0)
        if health_info is not None:
            break
        time.sleep(1.0)

    if health_info is None:
        print(f"Error: Server '{name}' timed out after {max_wait_s}s waiting for /health.")
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except OSError:
            pass
        return 1

    meta_data = {
        "name": name,
        "pid": proc.pid,
        "port": port,
        "model": health_info.get("model", ""),
        "backend": health_info.get("backend", ""),
        "started_at": int(time.time()),
        "log_path": str(log_file),
    }

    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta_data, f, indent=2)

    print(
        f"Server '{name}' is ready! PID: {proc.pid}, Port: {port}, "
        f"Model: {meta_data['model']}, Backend: {meta_data['backend']}"
    )
    return 0


def cmd_stop(name: str) -> int:
    meta_file = LOCAL_RUNS_DIR / f"{name}.json"
    pid: int | None = None

    if meta_file.exists():
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            pid = int(data.get("pid", 0))
        except Exception:
            pass

    if pid is None or not is_pid_alive(pid):
        # Also check if any process is listening on the default port
        port = SERVER_CONFIGS.get(name, {}).get("port")
        print(f"Server '{name}' is not currently running.")
        if meta_file.exists():
            meta_file.unlink()
        return 0

    print(f"Stopping server '{name}' (PID {pid})...")
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass

    # Wait up to 10 seconds for process termination
    for _ in range(10):
        if not is_pid_alive(pid):
            break
        time.sleep(1.0)

    if is_pid_alive(pid):
        print(f"Force-killing server '{name}' (PID {pid})...")
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except OSError:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    if meta_file.exists():
        meta_file.unlink()

    print(f"Server '{name}' stopped.")
    return 0


def cmd_status(name: str | None = None) -> int:
    targets = [name] if name else list(SERVER_CONFIGS.keys())
    active_name, active_data = get_active_server()

    print(f"{'Server':<12} | {'Status':<10} | {'PID':<8} | {'Port':<6} | {'Model':<30} | {'Backend'}")
    print("-" * 80)

    for target in targets:
        meta_file = LOCAL_RUNS_DIR / f"{target}.json"
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                pid = int(data.get("pid", 0))
                port = int(data.get("port", 0))
                if is_pid_alive(pid):
                    health = query_health(port)
                    status_str = "RUNNING" if health else "STARTING"
                    model = data.get("model", "")
                    backend = data.get("backend", "")
                    print(f"{target:<12} | {status_str:<10} | {pid:<8} | {port:<6} | {model:<30} | {backend}")
                    continue
            except Exception:
                pass
        port = SERVER_CONFIGS.get(target, {}).get("port", "-")
        print(f"{target:<12} | {'STOPPED':<10} | {'-':<8} | {port:<6} | {'-':<30} | {'-'}")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage edgebench local servers")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_p = subparsers.add_parser("start", help="Start a local server")
    start_p.add_argument("name", choices=["semif", "laya", "qwen_json"], help="Server name")
    start_p.add_argument("extra_args", nargs=argparse.REMAINDER, help="Extra arguments passed to server script")

    stop_p = subparsers.add_parser("stop", help="Stop a local server")
    stop_p.add_argument("name", choices=["semif", "laya", "qwen_json"], help="Server name")

    status_p = subparsers.add_parser("status", help="Status of local servers")
    status_p.add_argument("name", nargs="?", choices=["semif", "laya", "qwen_json"], help="Server name (optional)")

    args = parser.parse_args()

    if args.command == "start":
        sys.exit(cmd_start(args.name, args.extra_args or []))
    elif args.command == "stop":
        sys.exit(cmd_stop(args.name))
    elif args.command == "status":
        sys.exit(cmd_status(args.name))


if __name__ == "__main__":
    main()

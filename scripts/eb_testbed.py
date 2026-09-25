#!/usr/bin/env python3
"""Manage 3 Dockerised OCR worker testbed nodes (local, edge2, cloud) with traffic shaping.

Usage:
  scripts/eb_testbed.py up
  scripts/eb_testbed.py verify [--out testbed-verify.json]
  scripts/eb_testbed.py down
  scripts/eb_testbed.py status
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import urllib.request
from typing import Any

NODES = {
    "local": {
        "container_name": "edgebench-ocr-local",
        "port": 18764,
        "cpus": "1.0",
        "shaping": None,
        "role": "local",
    },
    "edge2": {
        "container_name": "edgebench-ocr-edge2",
        "port": 18765,
        "cpus": "1.0",
        "shaping": "tc qdisc add dev eth0 root netem delay 10ms rate 100mbit",
        "role": "edge2",
    },
    "cloud": {
        "container_name": "edgebench-ocr-cloud",
        "port": 18766,
        "cpus": "2.0",
        "shaping": "tc qdisc add dev eth0 root netem delay 30ms rate 50mbit",
        "role": "cloud",
    },
}

IMAGE_NAME = "edgebench-ocr-worker:latest"
DOCKERFILE_PATH = Path("configs/edgebench/ocr-worker/Dockerfile")


def is_container_running(name: str) -> bool:
    try:
        proc = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode == 0 and proc.stdout.strip() == "true"
    except Exception:
        return False


def stop_container(name: str) -> None:
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)


def wait_for_health(port: int, timeout_s: float = 15.0) -> dict[str, Any]:
    url = f"http://127.0.0.1:{port}/health"
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception:
            time.sleep(0.2)
    raise TimeoutError(f"Health check timed out after {timeout_s}s at {url}")


def up() -> None:
    print(f"Starting 3 testbed containers from image {IMAGE_NAME}...")
    for node, cfg in NODES.items():
        name = cfg["container_name"]
        port = cfg["port"]
        cpus = cfg["cpus"]
        shaping = cfg["shaping"]

        # Stop existing
        stop_container(name)

        # Run container
        cmd = [
            "docker", "run", "-d",
            "--name", name,
            "--cpus", cpus,
            "--cap-add", "NET_ADMIN",
            "-p", f"127.0.0.1:{port}:18764",
            IMAGE_NAME,
            "--node", node,
            "--port", "18764",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        container_id = proc.stdout.strip()[:12]

        # Apply traffic shaping if configured
        if shaping:
            time.sleep(0.5)
            shaping_cmd = ["docker", "exec", name] + shaping.split()
            subprocess.run(shaping_cmd, capture_output=True, text=True, check=True)

        health = wait_for_health(port)
        print(f"[{node}] running (container {container_id}, port {port}, cpus {cpus}, engine {health.get('engine')})")
        if shaping:
            print(f"       applied: {shaping}")

    print("All 3 testbed nodes are up and healthy.")


def down() -> None:
    print("Tearing down testbed containers...")
    for node, cfg in NODES.items():
        name = cfg["container_name"]
        stop_container(name)
        print(f"[{node}] stopped and removed.")
    print("Testbed is down.")


def status() -> None:
    print("Testbed Status:")
    for node, cfg in NODES.items():
        name = cfg["container_name"]
        port = cfg["port"]
        running = is_container_running(name)
        if running:
            try:
                health = wait_for_health(port, timeout_s=2.0)
                engine = health.get("engine", "unknown")
                # Check qdisc
                qdisc_proc = subprocess.run(
                    ["docker", "exec", name, "tc", "qdisc", "show", "dev", "eth0"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                qdisc = qdisc_proc.stdout.strip()
                print(f"[{node}] RUNNING on port {port} ({engine})")
                print(f"       qdisc: {qdisc}")
            except Exception as e:
                print(f"[{node}] RUNNING on port {port} but health check failed: {e}")
        else:
            print(f"[{node}] STOPPED")


def verify(out_path: str | Path = "testbed-verify.json") -> dict[str, Any]:
    print("Verifying testbed network properties (50 RTT samples + 2 MB upload throughput)...")
    results: dict[str, Any] = {}
    rtt_p50s: dict[str, float] = {}

    dummy_payload = b"X" * (2 * 1024 * 1024)  # Exactly 2 MB

    for node, cfg in NODES.items():
        port = cfg["port"]
        health_url = f"http://127.0.0.1:{port}/health"
        upload_url = f"http://127.0.0.1:{port}/upload"

        # 1. Measure 50 RTT samples
        rtt_samples: list[float] = []
        for _ in range(50):
            t0 = time.monotonic()
            req = urllib.request.Request(health_url)
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                resp.read()
            t1 = time.monotonic()
            rtt_samples.append((t1 - t0) * 1000.0)  # ms

        sorted_rtt = sorted(rtt_samples)
        p50 = statistics.median(sorted_rtt)
        p95 = sorted_rtt[int(round(49 * 0.95))]
        mean_rtt = statistics.mean(sorted_rtt)
        min_rtt = min(sorted_rtt)
        max_rtt = max(sorted_rtt)
        rtt_p50s[node] = p50

        # 2. Measure 2 MB upload throughput
        t0 = time.monotonic()
        upload_req = urllib.request.Request(
            upload_url,
            data=dummy_payload,
            headers={"Content-Type": "application/octet-stream"},
        )
        with urllib.request.urlopen(upload_req, timeout=15.0) as resp:
            resp.read()
        t1 = time.monotonic()
        upload_elapsed_s = t1 - t0
        upload_mbps = (2.0 * 8.0) / upload_elapsed_s

        results[node] = {
            "node": node,
            "port": port,
            "cpus": cfg["cpus"],
            "shaping": cfg["shaping"],
            "rtt_samples_ms": [round(x, 3) for x in rtt_samples],
            "rtt_p50_ms": round(p50, 3),
            "rtt_p95_ms": round(p95, 3),
            "rtt_mean_ms": round(mean_rtt, 3),
            "rtt_min_ms": round(min_rtt, 3),
            "rtt_max_ms": round(max_rtt, 3),
            "upload_2mb_elapsed_s": round(upload_elapsed_s, 4),
            "upload_throughput_mbps": round(upload_mbps, 2),
        }
        print(
            f"[{node}] RTT p50={p50:.2f}ms, p95={p95:.2f}ms | "
            f"2MB Upload: {upload_elapsed_s:.3f}s ({upload_mbps:.1f} Mbit/s)"
        )

    # Verify RTT ordering: local < edge2 < cloud
    ordered = rtt_p50s["local"] < rtt_p50s["edge2"] < rtt_p50s["cloud"]
    print(
        f"RTT Ordering check (local < edge2 < cloud): "
        f"{rtt_p50s['local']:.2f}ms < {rtt_p50s['edge2']:.2f}ms < {rtt_p50s['cloud']:.2f}ms => {ordered}"
    )
    if not ordered:
        raise AssertionError(
            f"RTT ordering violation: local={rtt_p50s['local']:.2f}ms, "
            f"edge2={rtt_p50s['edge2']:.2f}ms, cloud={rtt_p50s['cloud']:.2f}ms"
        )

    summary = {
        "status": "verified" if ordered else "failed",
        "rtt_ordering_verified": ordered,
        "nodes": results,
        "verified_at": time.time(),
    }

    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Verification results written to {out_file}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Dockerised OCR testbed.")
    parser.add_argument("action", choices=["up", "down", "verify", "status"])
    parser.add_argument("--out", default="testbed-verify.json", help="Path to write verification JSON")
    args = parser.parse_args()

    if args.action == "up":
        up()
    elif args.action == "down":
        down()
    elif args.action == "status":
        status()
    elif args.action == "verify":
        verify(args.out)


if __name__ == "__main__":
    main()

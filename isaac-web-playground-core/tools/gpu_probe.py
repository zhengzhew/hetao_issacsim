#!/usr/bin/env python3
"""Sample nvidia-smi and say what the playground actually costs.

Trimming settings without measuring them is guesswork, and this box has more
than one GPU, so "the GPU is busy" is not a useful sentence. Run this with the
service idle, run it again under load, and compare.

    # on the Isaac Sim machine
    python3 gpu_probe.py --seconds 20 --label idle    --out idle.json
    python3 gpu_probe.py --seconds 20 --label viewing --out viewing.json
    python3 gpu_probe.py --compare idle.json viewing.json

Standard library only, so it runs anywhere nvidia-smi does.
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
import time

GPU_FIELDS = ["index", "name", "utilization.gpu", "utilization.memory", "memory.used", "memory.total"]
PROC_FIELDS = ["gpu_uuid", "pid", "process_name", "used_gpu_memory"]


def nvidia_smi(query: list[str], mode: str = "--query-gpu") -> list[dict]:
    binary = shutil.which("nvidia-smi") or shutil.which("nvidia-smi.exe")
    if not binary:
        raise SystemExit("nvidia-smi is not on PATH. Run this on the machine with the GPU.")
    out = subprocess.run(
        [binary, f"{mode}={','.join(query)}", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=20,
    )
    if out.returncode != 0:
        raise SystemExit(f"nvidia-smi failed: {out.stderr.strip() or out.returncode}")
    rows = []
    for line in out.stdout.strip().splitlines():
        if not line.strip():
            continue
        values = [part.strip() for part in line.split(",")]
        rows.append(dict(zip(query, values)))
    return rows


def as_number(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def sample(seconds: float, interval: float, label: str) -> dict:
    first = nvidia_smi(GPU_FIELDS)
    gpus = {row["index"]: {"name": row["name"], "total_mb": as_number(row["memory.total"]),
                           "util": [], "mem_used_mb": []} for row in first}
    print(f"sampling {len(gpus)} GPU(s) for {seconds:g}s ...", flush=True)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        for row in nvidia_smi(GPU_FIELDS):
            entry = gpus.setdefault(row["index"], {"name": row["name"], "total_mb": as_number(row["memory.total"]),
                                                   "util": [], "mem_used_mb": []})
            entry["util"].append(as_number(row["utilization.gpu"]))
            entry["mem_used_mb"].append(as_number(row["memory.used"]))
        time.sleep(interval)

    try:
        processes = nvidia_smi(PROC_FIELDS, mode="--query-compute-apps")
    except SystemExit:
        processes = []

    result = {"label": label, "seconds": seconds, "gpus": {}, "processes": processes}
    for index, entry in sorted(gpus.items()):
        util = entry["util"] or [0.0]
        mem = entry["mem_used_mb"] or [0.0]
        result["gpus"][index] = {
            "name": entry["name"],
            "total_mb": entry["total_mb"],
            "util_mean": round(statistics.fmean(util), 1),
            "util_max": round(max(util), 1),
            "mem_mean_mb": round(statistics.fmean(mem), 1),
            "mem_max_mb": round(max(mem), 1),
            "samples": len(util),
        }
    return result


def show(result: dict) -> None:
    print(f"\n--- {result['label']} ({result['seconds']:g}s) ---")
    for index, gpu in result["gpus"].items():
        print(f"  GPU {index}  {gpu['name']}")
        print(f"    util  mean {gpu['util_mean']:5.1f}%   max {gpu['util_max']:5.1f}%")
        print(f"    mem   mean {gpu['mem_mean_mb']:8.0f} MB  max {gpu['mem_max_mb']:8.0f} MB "
              f"of {gpu['total_mb']:.0f} MB")
    if result["processes"]:
        print("  processes holding GPU memory:")
        for proc in result["processes"]:
            print(f"    pid {proc.get('pid'):>7}  {proc.get('used_gpu_memory'):>7} MB  {proc.get('process_name')}")


def compare(before: dict, after: dict) -> None:
    print(f"\n--- {before['label']}  ->  {after['label']} ---")
    for index, gpu in after["gpus"].items():
        base = before["gpus"].get(index)
        if not base:
            continue
        d_util = gpu["util_mean"] - base["util_mean"]
        d_mem = gpu["mem_mean_mb"] - base["mem_mean_mb"]
        print(f"  GPU {index}  {gpu['name']}")
        print(f"    util  {base['util_mean']:5.1f}% -> {gpu['util_mean']:5.1f}%   ({d_util:+.1f} points)")
        print(f"    mem   {base['mem_mean_mb']:7.0f} -> {gpu['mem_mean_mb']:7.0f} MB  ({d_mem:+.0f} MB)")
    print("\n  A difference smaller than a few points is noise; take a longer sample.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seconds", type=float, default=15.0)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--label", default="sample")
    parser.add_argument("--out", help="write the sample as JSON")
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    args = parser.parse_args()

    if args.compare:
        with open(args.compare[0], encoding="utf-8") as a, open(args.compare[1], encoding="utf-8") as b:
            compare(json.load(a), json.load(b))
        return 0

    result = sample(args.seconds, args.interval, args.label)
    show(result)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

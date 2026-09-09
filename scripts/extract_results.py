#!/usr/bin/env python3
"""
Extract mesh statistics, tool geometry, field ranges and derived process
quantities directly from the Ansys Fluent case and data files.

The Fluent .cas.h5 / .dat.h5 files are plain HDF5 containers, so everything
below is read with h5py alone. Fluent itself is not required.

Usage
-----
    python scripts/extract_results.py
    python scripts/extract_results.py --case path/to/case.cas.h5 \
                                      --data path/to/data.dat.h5 \
                                      --json results/summary.json
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import h5py
import numpy as np

# Process inputs, as set in the Fluent session (see docs/fluent-setup-report.xml).
OMEGA_RAD_S = 74.351      # tool rotation speed imposed on the fswtool wall
TRAVERSE_M_S = 0.00133    # inlet velocity, equal to the weld traverse speed

# AA6061 melting range, used only to report the peak temperature as a fraction.
SOLIDUS_K = 855.0         # 582 C
LIQUIDUS_K = 925.0        # 652 C

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASE = REPO_ROOT / "simulation" / "fluent" / "FFF-1.cas.h5"
DEFAULT_DATA = REPO_ROOT / "simulation" / "fluent" / "FFF-1-00352.dat.h5"


def face_zone_bounds(case: h5py.File) -> dict[str, tuple[int, int]]:
    """Map each face zone name to its inclusive (minId, maxId) face range."""
    topo = case["meshes/1/faces/zoneTopology"]
    raw = topo["name"][0]
    names = raw.decode() if isinstance(raw, bytes) else str(raw)
    names = names.split(";")
    lo = topo["minId"][:].astype(np.int64)
    hi = topo["maxId"][:].astype(np.int64)
    return {n: (int(a), int(b)) for n, a, b in zip(names, lo, hi)}


def zone_node_coords(case: h5py.File, first: int, last: int) -> np.ndarray:
    """Return the coordinates of every node touched by faces [first, last]."""
    coords = case["meshes/1/nodes/coords/4"][:]
    counts = case["meshes/1/faces/nodes/1/nnodes"][:]
    conn = case["meshes/1/faces/nodes/1/nodes"][:] - 1  # Fluent is 1-based
    offsets = np.zeros(len(counts) + 1, dtype=np.int64)
    np.cumsum(counts, out=offsets[1:])
    node_ids = np.unique(conn[offsets[first - 1]: offsets[last]])
    return coords[node_ids]


def describe_tool(case: h5py.File, zones: dict[str, tuple[int, int]]) -> dict:
    """Recover shoulder and pin dimensions from the fswtool wall zone."""
    pts = zone_node_coords(case, *zones["fswtool"])
    radius = np.hypot(pts[:, 0], pts[:, 1])
    depth = pts[:, 2]

    on_top = np.abs(depth) < 1e-9
    below_top = depth < -1e-9

    return {
        "shoulder_diameter_mm": round(float(radius[on_top].max()) * 2e3, 3),
        "pin_diameter_mm": round(float(radius[below_top].max()) * 2e3, 3),
        "pin_length_mm": round(float(-depth.min()) * 1e3, 3),
    }


def describe_domain(case: h5py.File) -> dict:
    coords = case["meshes/1/nodes/coords/4"][:]
    extent = (coords.max(axis=0) - coords.min(axis=0)) * 1e3
    mesh = case["meshes/1"]
    return {
        "plate_length_mm": round(float(extent[0]), 3),
        "plate_width_mm": round(float(extent[1]), 3),
        "plate_thickness_mm": round(float(extent[2]), 3),
        "cells": int(mesh.attrs["cellCount"][0]),
        "faces": int(mesh.attrs["faceCount"][0]),
        "nodes": int(mesh.attrs["nodeCount"][0]),
    }


def describe_fields(data: h5py.File) -> dict:
    cells = data["results/1/phase-1/cells"]

    temp = cells["SV_T/1"][:]
    visc = cells["SV_MU_LAM/1"][:]
    u = cells["SV_U/1"][:]
    v = cells["SV_V/1"][:]
    w = cells["SV_W/1"][:]
    speed = np.sqrt(u * u + v * v + w * w)

    return {
        "temperature_min_K": round(float(temp.min()), 2),
        "temperature_max_K": round(float(temp.max()), 2),
        "viscosity_min_Pa_s": round(float(visc.min()), 1),
        "viscosity_max_Pa_s": round(float(visc.max()), 1),
        "velocity_max_m_s": round(float(speed.max()), 5),
    }


def read_monitor_tail(path: Path) -> tuple[int, float] | None:
    """Return (last iteration, last value) from a Fluent report-file plot."""
    if not path.exists():
        return None
    last = None
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) == 2:
            try:
                last = (int(parts[0]), float(parts[1]))
            except ValueError:
                continue
    return last


def describe_loads(monitor_dir: Path) -> dict:
    out: dict[str, float | int] = {}
    for name, key in [
        ("torque", "tool_torque_N_m"),
        ("weldforce", "weld_force_N"),
        ("lateralforce", "lateral_force_N"),
        ("thrustforce", "thrust_force_N"),
    ]:
        tail = read_monitor_tail(monitor_dir / f"{name}-rfile.out")
        if tail is not None:
            out["iterations"] = tail[0]
            out[key] = round(abs(tail[1]), 4)
    return out


def derive(loads: dict, fields: dict) -> dict:
    torque = loads.get("tool_torque_N_m")
    if torque is None:
        return {}
    power = torque * OMEGA_RAD_S
    return {
        "rotation_speed_rpm": round(OMEGA_RAD_S * 60.0 / (2.0 * math.pi), 1),
        "traverse_speed_mm_min": round(TRAVERSE_M_S * 60_000.0, 2),
        "revolutions_per_mm": round(
            (OMEGA_RAD_S * 60.0 / (2.0 * math.pi)) / (TRAVERSE_M_S * 60_000.0), 2
        ),
        "shoulder_edge_speed_m_s": None,  # filled in by main once geometry is known
        "spindle_power_W": round(power, 1),
        "heat_input_kJ_per_mm": round(power / TRAVERSE_M_S / 1e6, 3),
        "peak_T_over_solidus": round(fields["temperature_max_K"] / SOLIDUS_K, 3),
        "peak_T_over_liquidus": round(fields["temperature_max_K"] / LIQUIDUS_K, 3),
        "peak_T_celsius": round(fields["temperature_max_K"] - 273.15, 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", type=Path, default=DEFAULT_CASE)
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA)
    ap.add_argument("--monitors", type=Path,
                    default=REPO_ROOT / "results" / "monitors")
    ap.add_argument("--json", type=Path,
                    default=REPO_ROOT / "results" / "summary.json")
    args = ap.parse_args()

    with h5py.File(args.case, "r") as case:
        zones = face_zone_bounds(case)
        domain = describe_domain(case)
        tool = describe_tool(case, zones)

    with h5py.File(args.data, "r") as data:
        fields = describe_fields(data)

    loads = describe_loads(args.monitors)
    derived = derive(loads, fields)
    derived["shoulder_edge_speed_m_s"] = round(
        OMEGA_RAD_S * tool["shoulder_diameter_mm"] / 2e3, 4
    )

    summary = {
        "domain": domain,
        "tool": tool,
        "boundary_zones": sorted(zones),
        "fields": fields,
        "converged_loads": loads,
        "derived": derived,
    }

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(summary, indent=2) + "\n")

    width = 34
    for section, block in summary.items():
        print(f"\n{section.replace('_', ' ').upper()}")
        if isinstance(block, list):
            print("  " + ", ".join(block))
            continue
        for k, val in block.items():
            print(f"  {k:<{width}} {val}")
    print(f"\nWritten to {args.json.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()

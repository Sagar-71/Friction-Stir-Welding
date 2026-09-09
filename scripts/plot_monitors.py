#!/usr/bin/env python3
"""
Plot the convergence history of the tool torque and the three tool force
components from the Fluent report-file monitors.

Fluent report files start with a few header lines, then one
"iteration value" pair per line. Only the pair lines are parsed.

Usage
-----
    python scripts/plot_monitors.py
    python scripts/plot_monitors.py --skip 20 --outdir results/figures
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

MONITORS = [
    ("torque", "Tool torque", "N.m"),
    ("weldforce", "Weld (traverse) force", "N"),
    ("lateralforce", "Lateral force", "N"),
    ("thrustforce", "Thrust force", "N"),
]


def read_monitor(path: Path) -> tuple[list[int], list[float]]:
    iters: list[int] = []
    vals: list[float] = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            i, v = int(parts[0]), float(parts[1])
        except ValueError:
            continue
        iters.append(i)
        vals.append(v)
    if not iters:
        raise ValueError(f"no numeric data found in {path}")
    return iters, vals


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--monitors", type=Path,
                    default=REPO_ROOT / "results" / "monitors")
    ap.add_argument("--outdir", type=Path,
                    default=REPO_ROOT / "results" / "figures")
    ap.add_argument("--skip", type=int, default=25,
                    help="drop the first N iterations, whose startup "
                         "transients otherwise dominate the y-axis")
    args = ap.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    for ax, (stem, label, unit) in zip(axes.ravel(), MONITORS):
        path = args.monitors / f"{stem}-rfile.out"
        if not path.exists():
            ax.set_axis_off()
            continue

        iters, vals = read_monitor(path)
        keep = [k for k, i in enumerate(iters) if i > args.skip]
        x = [iters[k] for k in keep]
        y = [abs(vals[k]) for k in keep]

        ax.plot(x, y, linewidth=1.4, color="#1f4e79")
        ax.axhline(y[-1], linestyle="--", linewidth=0.9, color="#c00000")
        ax.annotate(
            f"{y[-1]:.3f} {unit}",
            xy=(x[-1], y[-1]),
            xytext=(-8, 8),
            textcoords="offset points",
            ha="right",
            fontsize=9,
            color="#c00000",
        )
        ax.set_title(f"{label} (magnitude)", fontsize=10)
        ax.set_xlabel("Iteration")
        ax.set_ylabel(f"{label} [{unit}]")
        ax.grid(alpha=0.3)

    fig.suptitle(
        "Friction stir welding, AA6061: converged tool loads "
        f"(iterations {args.skip + 1} onward)",
        fontsize=12,
    )
    fig.tight_layout()

    out = args.outdir / "tool-load-convergence.png"
    fig.savefig(out, dpi=160)
    print(f"Written to {out.relative_to(REPO_ROOT)}")

    for stem, label, unit in MONITORS:
        path = args.monitors / f"{stem}-rfile.out"
        if path.exists():
            _, vals = read_monitor(path)
            print(f"  {label:<24} {abs(vals[-1]):>10.4f} {unit}")


if __name__ == "__main__":
    main()

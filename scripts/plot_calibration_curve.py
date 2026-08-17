"""Create a slide-ready coverage-versus-selective-accuracy calibration chart."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--policy-file",
        type=Path,
        default=Path("artifacts/phase6_calibrated_policy.json"),
        help="Field-specific calibration output created by calibrate_thresholds.py",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/figures/calibration_coverage_accuracy.png"),
        help="PNG output for slides",
    )
    parser.add_argument(
        "--svg-output",
        type=Path,
        default=Path("artifacts/figures/calibration_coverage_accuracy.svg"),
        help="SVG output for high-resolution slide editing",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.policy_file.is_file():
        print(f"Policy file does not exist: {args.policy_file}", file=sys.stderr)
        return 2
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("Matplotlib is not installed. Run `pip install -e .[plots]`.", file=sys.stderr)
        return 1

    payload = json.loads(args.policy_file.read_text(encoding="utf-8"))
    curves = payload.get("coverage_accuracy_curves_by_field")
    selections = payload.get("field_selection")
    if not isinstance(curves, dict) or not isinstance(selections, dict):
        print("Policy file does not contain field-specific calibration curves.", file=sys.stderr)
        return 2

    target = float(payload["target_selective_accuracy"])
    colours = {"company": "#4C78A8", "address": "#E45756", "date": "#2A9D8F", "total": "#F2A541"}
    labels = {"company": "Company", "address": "Address", "date": "Date", "total": "Total"}

    figure, axis = plt.subplots(figsize=(10.5, 6.5), constrained_layout=True)
    axis.axhline(target * 100, color="#555555", linewidth=1.5, linestyle="--", label=f"Target: {target:.0%}")

    for field, rows in curves.items():
        usable = [row for row in rows if row.get("coverage") is not None and row.get("selective_accuracy") is not None]
        if not usable:
            continue
        x_values = [row["coverage"] * 100 for row in usable]
        y_values = [row["selective_accuracy"] * 100 for row in usable]
        axis.plot(
            x_values,
            y_values,
            color=colours.get(field, "#777777"),
            linewidth=2.3,
            marker="o",
            markersize=3.5,
            alpha=0.9,
            label=labels.get(field, field.title()),
        )

        selection = selections.get(field, {})
        if selection.get("target_met"):
            selected = selection["selected"]
            axis.scatter(
                selected["coverage"] * 100,
                selected["selective_accuracy"] * 100,
                color=colours.get(field, "#111111"),
                edgecolor="white",
                linewidth=1.4,
                s=140,
                zorder=5,
            )
            axis.annotate(
                f"Selected {labels.get(field, field.title())}\nthreshold {selected['accept_threshold']:.2f}",
                xy=(selected["coverage"] * 100, selected["selective_accuracy"] * 100),
                xytext=(14, -38),
                textcoords="offset points",
                fontsize=10,
                color=colours.get(field, "#111111"),
                arrowprops={"arrowstyle": "-", "color": colours.get(field, "#111111")},
            )

    disabled = [labels.get(field, field.title()) for field, selection in selections.items() if not selection.get("target_met")]
    if disabled:
        axis.text(
            0.99,
            0.03,
            "Automatic acceptance disabled:\n" + ", ".join(disabled),
            transform=axis.transAxes,
            ha="right",
            va="bottom",
            fontsize=10,
            bbox={"boxstyle": "round,pad=0.5", "facecolor": "#F4F4F4", "edgecolor": "#BBBBBB"},
        )

    axis.set_title("Calibration: Coverage vs Selective Accuracy", fontsize=17, weight="bold", pad=14)
    axis.set_xlabel("Automation coverage within field (%)", fontsize=12)
    axis.set_ylabel("Selective accuracy among accepted values (%)", fontsize=12)
    axis.set_xlim(left=0)
    axis.set_ylim(0, 105)
    axis.grid(axis="both", color="#E5E5E5", linewidth=0.8)
    # Keep the legend outside the axes: all curves begin near 100% accuracy,
    # so an in-chart legend would hide the most important evidence.
    axis.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.14),
        frameon=False,
        ncol=3,
        columnspacing=1.6,
    )

    for output in (args.output, args.svg_output):
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(figure)
    print(f"Saved PNG chart to: {args.output}")
    print(f"Saved SVG chart to: {args.svg_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

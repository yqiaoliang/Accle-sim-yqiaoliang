#!/usr/bin/env python3

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

# Set this to a confluence directory or either CSV path, then run:
#   python3 script/plot_config_csv.py
result_path = "/Users/bytedance/Desktop/Accel-sim/accel-sim-framework/regress_result/20260612_064245/confluence"

ACTIVE_STAGES = ["SCHEDULER", "OPERAND_COLLECTOR", "EXECUTION_PIPELINE", "WRITEBACK"]
STAGE_COLORS = {
    "SCHEDULER": "#4c78a8",
    "OPERAND_COLLECTOR": "#f58518",
    "EXECUTION_PIPELINE": "#54a24b",
    "WRITEBACK": "#e45756",
    "TOTAL": "#72b7b2",
}


def load_pyplot():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def percent(value, total):
    return value / total * 100 if total else 0.0


def parse_percent(value):
    return float(str(value).strip().rstrip("%") or 0)


def short_config_name(name):
    text = str(name)
    match = re.search(
        r"sched_(?P<sched>[^_]+)_rfc(?P<rfc>\d+)_bank(?P<bank>\d+)_wbd(?P<wbd>\d+)_reuse(?P<reuse>\d+)_ocs(?P<ocs>\d+)_regb(?P<regb>\d+)_ocu(?P<ocu>\d+)",
        text,
    )
    if not match:
        return text
    g = match.groupdict()
    return (
        f"{g['sched']} rfc{g['rfc']} bank{g['bank']} wbd{g['wbd']} "
        f"reuse{g['reuse']} ocs{g['ocs']} regb{g['regb']} ocu{g['ocu']}"
    )


def add_bar_labels(ax, bars, values, fmt="{:.1f}"):
    for bar, value in zip(bars, values):
        if value == 0:
            continue
        ax.annotate(
            fmt.format(value),
            xy=(bar.get_width(), bar.get_y() + bar.get_height() / 2),
            xytext=(4, 0),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=7,
        )


def read_remain_cycles(csv_path):
    data = defaultdict(lambda: defaultdict(dict))
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            case = row["case"]
            op = row["op"]
            stage = row["stage"]
            data[op][case][stage] = {
                "count": int(float(row["count"] or 0)),
                "avg": float(row["avg_remain_cycles"] or 0),
                "median": float(row["median_remain_cycles"] or 0),
            }
    return data


def read_stage_stall_remain(csv_path):
    data = defaultdict(lambda: defaultdict(dict))
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            data[row["op"]][row["case"]][row["stage"]] = {
                "stall": int(float(row["stall"] or 0)),
                "stall_pct": parse_percent(row["stall_%"]),
                "remain": int(float(row["remain"] or 0)),
                "remain_pct": parse_percent(row["remain_%"]),
            }
    return data


def sorted_ops(data):
    return sorted(data.keys(), key=lambda op: sum(
        item.get("TOTAL", {}).get("avg", 0) if "TOTAL" in item else sum(stage.get("remain", 0) for stage in item.values())
        for item in data[op].values()
    ), reverse=True)


def plot_remain_cycles(data, metric, output_path, max_cases=None):
    plt = load_pyplot()
    ops = sorted_ops(data)
    if not ops:
        return
    fig_height = max(6, len(ops) * 3.2)
    fig, axes = plt.subplots(len(ops), 1, figsize=(18, fig_height), squeeze=False, constrained_layout=True)
    stages = ACTIVE_STAGES + ["TOTAL"]

    for ax, op in zip(axes[:, 0], ops):
        cases = sorted(data[op], key=lambda case: data[op][case].get("TOTAL", {}).get(metric, 0), reverse=True)
        if max_cases:
            cases = cases[:max_cases]
        labels = [short_config_name(case) for case in cases]
        y_pos = list(range(len(cases)))
        lefts = [0.0] * len(cases)

        for stage in stages:
            values = [data[op][case].get(stage, {}).get(metric, 0.0) for case in cases]
            if stage == "TOTAL":
                continue
            bars = ax.barh(y_pos, values, left=lefts, label=stage, color=STAGE_COLORS.get(stage))
            lefts = [lefts[i] + values[i] for i in range(len(values))]

        total_values = [data[op][case].get("TOTAL", {}).get(metric, lefts[i]) for i, case in enumerate(cases)]
        for y, total in zip(y_pos, total_values):
            ax.text(max(lefts[y], total) * 1.005 if max(lefts[y], total) else 0, y, f"total={total:,.1f}", ha="left", va="center", fontsize=7)

        ax.set_title(f"{op} {metric} remain cycles")
        ax.set_xlabel("remain cycles")
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=7)
        ax.invert_yaxis()
        ax.legend(loc="lower right", fontsize=7)

    fig.suptitle(f"config op {metric} remain cycles")
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_stage_ratio(data, metric, output_path, max_cases=None):
    plt = load_pyplot()
    ops = sorted_ops(data)
    if not ops:
        return
    fig_height = max(6, len(ops) * 3.2)
    fig, axes = plt.subplots(len(ops), 1, figsize=(18, fig_height), squeeze=False, constrained_layout=True)

    for ax, op in zip(axes[:, 0], ops):
        cases = sorted(
            data[op],
            key=lambda case: sum(data[op][case].get(stage, {}).get(metric, 0) for stage in ACTIVE_STAGES),
            reverse=True,
        )
        if max_cases:
            cases = cases[:max_cases]
        labels = [short_config_name(case) for case in cases]
        y_pos = list(range(len(cases)))
        lefts = [0.0] * len(cases)
        totals = [sum(data[op][case].get(stage, {}).get(metric, 0) for stage in ACTIVE_STAGES) for case in cases]

        for stage in ACTIVE_STAGES:
            raw_values = [data[op][case].get(stage, {}).get(metric, 0) for case in cases]
            values = [percent(value, total) for value, total in zip(raw_values, totals)]
            bars = ax.barh(y_pos, values, left=lefts, label=stage, color=STAGE_COLORS.get(stage))
            for bar, ratio, raw in zip(bars, values, raw_values):
                if ratio >= 6:
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        bar.get_y() + bar.get_height() / 2,
                        f"{ratio:.1f}%\n{raw:,.0f}",
                        ha="center",
                        va="center",
                        fontsize=6,
                    )
            lefts = [lefts[i] + values[i] for i in range(len(values))]

        for y, total in zip(y_pos, totals):
            ax.text(101, y, f"total={total:,.0f}", ha="left", va="center", fontsize=7)

        ax.set_title(f"{op} {metric} stage ratio")
        ax.set_xlabel("ratio (%)")
        ax.set_xlim(0, 118)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=7)
        ax.invert_yaxis()
        ax.legend(loc="lower right", fontsize=7)

    fig.suptitle(f"config op stage {metric} ratio")
    fig.savefig(output_path, dpi=180)
    plt.close(fig)



def main():
    parser = argparse.ArgumentParser(description="Plot config_op_remain_cycles.csv and config_op_stage_stall_remain.csv.")
    parser.add_argument("path", nargs="?", help="confluence directory or one csv path; overrides result_path")
    parser.add_argument("--output-dir", help="directory for generated png files")
    parser.add_argument("--max-cases", type=int, default=0, help="keep only top N configs per op; default keeps all")
    args = parser.parse_args()

    selected_path = args.path or result_path
    if not selected_path:
        raise SystemExit("Please set result_path at the top of this script, or pass a confluence directory / CSV path.")

    input_path = Path(selected_path)
    if input_path.is_dir():
        confluence_dir = input_path
    else:
        confluence_dir = input_path.parent

    remain_csv = confluence_dir / "config_op_remain_cycles.csv"
    stage_csv = confluence_dir / "config_op_stage_stall_remain.csv"
    output_dir = Path(args.output_dir) if args.output_dir else confluence_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    max_cases = args.max_cases or None

    if remain_csv.exists():
        remain_data = read_remain_cycles(remain_csv)
        plot_remain_cycles(remain_data, "avg", output_dir / "config_op_avg_remain_cycles_long.png", max_cases)
        plot_remain_cycles(remain_data, "median", output_dir / "config_op_median_remain_cycles_long.png", max_cases)
    else:
        print(f"skip missing {remain_csv}")

    if stage_csv.exists():
        stage_data = read_stage_stall_remain(stage_csv)
        plot_stage_ratio(stage_data, "stall", output_dir / "config_op_stage_stall_ratio_long.png", max_cases)
        plot_stage_ratio(stage_data, "remain", output_dir / "config_op_stage_remain_ratio_long.png", max_cases)
    else:
        print(f"skip missing {stage_csv}")

    print(f"plots written to {output_dir}")


if __name__ == "__main__":
    main()

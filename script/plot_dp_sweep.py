#!/usr/bin/env python3

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

# Set this to the DP sweep result directory, then run:
#   python3 script/plot_dp_sweep.py
result_path = "/Users/bytedance/Desktop/Accel-sim/accel-sim-framework/regress_result/20260612_064245"

TARGET_STAGE = "OPERAND_COLLECTOR"


def load_pyplot():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def extract_param(name, key):
    match = re.search(rf"{key}(\d+)", str(name))
    return int(match.group(1)) if match else None


def short_case_name(name):
    return str(name).split("-rodinia")[0]


def read_gpu_tot_sim_cycle(log_path):
    patterns = [
        re.compile(r"gpu_tot_sim_cycle\s*=\s*(\d+)"),
        re.compile(r"gpu_sim_cycle\s*=\s*(\d+)"),
    ]
    text = log_path.read_text(errors="ignore")
    for pattern in patterns:
        matches = pattern.findall(text)
        if matches:
            return int(matches[-1])
    return None


def collect_case_cycles(result_root):
    cycles = defaultdict(dict)
    for config_dir in Path(result_root).glob("regress_sched_*"):
        ocs = extract_param(config_dir.name, "ocs")
        dp = extract_param(config_dir.name, "dp")
        if ocs is None or dp is None:
            continue
        for log_path in config_dir.glob("*/*.log"):
            cycle = read_gpu_tot_sim_cycle(log_path)
            if cycle is not None:
                cycles[log_path.parent.name][(ocs, dp)] = cycle
    return cycles


def collect_op_stage_metrics(result_root):
    remain = defaultdict(lambda: defaultdict(int))
    stall = defaultdict(lambda: defaultdict(int))

    for csv_path in Path(result_root).glob("regress_sched_*/confluence/case_op_stage_stall_remain.csv"):
        config = csv_path.parent.parent.name
        ocs = extract_param(config, "ocs")
        dp = extract_param(config, "dp")
        if ocs is None or dp is None:
            continue
        key = (ocs, dp)
        with open(csv_path, newline="") as f:
            for row in csv.DictReader(f):
                if row["stage"] != TARGET_STAGE:
                    continue
                op = row["op"]
                remain[op][key] += int(float(row["remain"] or 0))
                stall[op][key] += int(float(row["stall"] or 0))

    return remain, stall


def plot_metric_by_op(metric_data, output_path, metric_name, colors):
    plt = load_pyplot()
    ops = sorted(
        metric_data,
        key=lambda op: sum(metric_data[op].values()),
        reverse=True,
    )
    if not ops:
        raise SystemExit("No DP sweep metric data found.")

    all_keys = sorted({key for op_data in metric_data.values() for key in op_data})
    ocs_values = sorted({ocs for ocs, _ in all_keys})
    dp_values = sorted({dp for _, dp in all_keys})

    ncols = 2
    nrows = (len(ops) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(20, max(8, nrows * 4.2)), squeeze=False, constrained_layout=True)
    width = 0.75 / max(1, len(dp_values))
    offsets = [(i - (len(dp_values) - 1) / 2) * width for i in range(len(dp_values))]

    for idx, op in enumerate(ops):
        ax = axes[idx // ncols][idx % ncols]
        op_data = metric_data[op]
        baseline = op_data.get((max(ocs_values), min(dp_values))) or next((v for _, v in sorted(op_data.items()) if v), None)
        max_value_m = max((op_data.get((ocs, dp), 0) / 1_000_000 for ocs in ocs_values for dp in dp_values), default=0)

        for color, dp, offset in zip(colors[:len(dp_values)], dp_values, offsets):
            values = [op_data.get((ocs, dp), 0) for ocs in ocs_values]
            values_m = [value / 1_000_000 for value in values]
            x_positions = [ocs + offset for ocs in ocs_values]
            bars = ax.bar(
                x_positions,
                values_m,
                width=width,
                label=f"dp{dp}",
                color=color,
                edgecolor="#333333",
                linewidth=0.6,
                alpha=1.0,
            )
            labels = []
            for value in values:
                if value == 0:
                    labels.append("")
                elif baseline:
                    labels.append(f"{value/1_000_000:.2f}M\n{value/baseline:.2f}x")
                else:
                    labels.append(f"{value/1_000_000:.2f}M")
            ax.bar_label(bars, labels=labels, padding=3, fontsize=6.5)

        ax.set_title(op, fontsize=10, fontweight="bold")
        ax.set_xlabel("ocs / RFC count")
        ax.set_ylabel(f"OC/RFC {metric_name} cycles (M)")
        ax.set_xticks(ocs_values)
        ax.set_ylim(0, max_value_m * 1.38 if max_value_m > 0 else 1)
        ax.grid(axis="y", linestyle="--", alpha=0.25)
        ax.legend(fontsize=7)

    for idx in range(len(ops), nrows * ncols):
        axes[idx // ncols][idx % ncols].axis("off")

    fig.suptitle(f"DP sweep: per-op OC/RFC {metric_name} cycles", fontsize=14)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_case_cycles(cycles, output_path, colors):
    plt = load_pyplot()
    cases = sorted(cycles, key=short_case_name)
    if not cases:
        raise SystemExit("No case cycle data found.")

    all_keys = sorted({key for case_data in cycles.values() for key in case_data})
    ocs_values = sorted({ocs for ocs, _ in all_keys})
    dp_values = sorted({dp for _, dp in all_keys})
    baseline_dp = min(dp_values)
    ncols = 2
    nrows = (len(cases) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(22, max(10, nrows * 4.2)), squeeze=False, constrained_layout=True)
    width = 0.75 / max(1, len(dp_values))
    offsets = [(i - (len(dp_values) - 1) / 2) * width for i in range(len(dp_values))]

    for idx, case in enumerate(cases):
        ax = axes[idx // ncols][idx % ncols]
        case_data = cycles[case]
        max_cycle_m = max((case_data.get((ocs, dp), 0) / 1_000_000 for ocs in ocs_values for dp in dp_values), default=0)

        for color, dp, offset in zip(colors[:len(dp_values)], dp_values, offsets):
            values = [case_data.get((ocs, dp), 0) for ocs in ocs_values]
            values_m = [value / 1_000_000 for value in values]
            x_positions = [ocs + offset for ocs in ocs_values]
            bars = ax.bar(
                x_positions,
                values_m,
                width=width,
                label=f"dp{dp}",
                color=color,
                edgecolor="#333333",
                linewidth=0.6,
                alpha=1.0,
            )
            labels = []
            for ocs, value in zip(ocs_values, values):
                if value == 0:
                    labels.append("")
                    continue
                baseline = case_data.get((ocs, baseline_dp))
                if baseline:
                    labels.append(f"{value/1_000_000:.2f}M\n{value/baseline:.3f}x")
                else:
                    labels.append(f"{value/1_000_000:.2f}M")
            ax.bar_label(bars, labels=labels, padding=3, fontsize=6.5)

        ax.set_title(short_case_name(case), fontsize=10, fontweight="bold")
        ax.set_xlabel("ocs / RFC count")
        ax.set_ylabel("gpu_tot_sim_cycle (M)")
        ax.set_xticks(ocs_values)
        ax.set_ylim(0, max_cycle_m * 1.38 if max_cycle_m > 0 else 1)
        ax.grid(axis="y", linestyle="--", alpha=0.25)
        ax.legend(fontsize=7)

    for idx in range(len(cases), nrows * ncols):
        axes[idx // ncols][idx % ncols].axis("off")

    fig.suptitle(f"DP sweep: per-case total cycles, ratio vs dp{baseline_dp} at same ocs", fontsize=14)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Plot per-op OC/RFC remain and stall cycles for DP unit sweep.")
    parser.add_argument("path", nargs="?", help="DP sweep result directory; overrides result_path")
    parser.add_argument("--output-dir", help="directory for generated png files; default uses sweep confluence directory")
    args = parser.parse_args()

    selected_path = args.path or result_path
    if not selected_path:
        raise SystemExit("Please set result_path at the top of this script, or pass a DP sweep result path.")

    result_root = Path(selected_path)
    output_dir = Path(args.output_dir) if args.output_dir else result_root / "confluence"
    output_dir.mkdir(parents=True, exist_ok=True)

    remain, stall = collect_op_stage_metrics(result_root)
    cycles = collect_case_cycles(result_root)
    remain_path = output_dir / "dp_sweep_op_oc_remain_by_op_subplots.png"
    stall_path = output_dir / "dp_sweep_op_oc_stall_by_op_subplots.png"
    cycle_path = output_dir / "dp_sweep_case_total_cycle_by_case_subplots.png"
    remain_colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd", "#8c564b"]
    stall_colors = ["#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f"]
    cycle_colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd", "#8c564b"]
    plot_metric_by_op(remain, remain_path, "remain", remain_colors)
    plot_metric_by_op(stall, stall_path, "stall", stall_colors)
    plot_case_cycles(cycles, cycle_path, cycle_colors)
    print(f"plot written to {remain_path}")
    print(f"plot written to {stall_path}")
    print(f"plot written to {cycle_path}")


if __name__ == "__main__":
    main()

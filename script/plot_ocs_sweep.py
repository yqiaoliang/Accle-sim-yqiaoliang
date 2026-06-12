#!/usr/bin/env python3

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

# Set this to the sweep result directory or its confluence directory, then run:
#   python3 script/plot_ocs_sweep.py
result_path = "/Users/bytedance/Desktop/Accel-sim/accel-sim-framework/regress_result/20260612_064245/confluence"
baseline_ocs = 2

ACTIVE_STAGES = ["SCHEDULER", "OPERAND_COLLECTOR", "EXECUTION_PIPELINE", "WRITEBACK"]
STAGE_COLORS = {
    "SCHEDULER": "#4c78a8",
    "OPERAND_COLLECTOR": "#f58518",
    "EXECUTION_PIPELINE": "#54a24b",
    "WRITEBACK": "#e45756",
}


def load_pyplot():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def percent(value, total):
    return value / total * 100 if total else 0.0


def short_case_name(name):
    return str(name).split("-rodinia")[0]


def extract_ocs(name):
    match = re.search(r"ocs(?P<ocs>\d+)", str(name))
    return int(match.group("ocs")) if match else None


def resolve_result_root(path):
    p = Path(path)
    if p.name == "confluence":
        return p.parent
    return p


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


def collect_sweep_data(result_root):
    stage_remain = defaultdict(lambda: defaultdict(lambda: {stage: 0 for stage in ACTIVE_STAGES}))
    load_remain = defaultdict(lambda: defaultdict(int))
    op_counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    op_oc_remain = defaultdict(lambda: defaultdict(int))
    op_oc_stall = defaultdict(lambda: defaultdict(int))
    total_cycles = defaultdict(dict)

    for stage_csv in result_root.glob("regress_sched_*/confluence/case_op_stage_stall_remain.csv"):
        config_dir = stage_csv.parent.parent
        ocs = extract_ocs(config_dir.name)
        if ocs is None:
            continue

        with open(stage_csv, newline="") as f:
            for row in csv.DictReader(f):
                stage = row["stage"]
                if stage in ACTIVE_STAGES:
                    remain = int(float(row["remain"] or 0))
                    stage_remain[row["case"]][ocs][stage] += remain
                    if stage == "OPERAND_COLLECTOR":
                        op_oc_remain[ocs][row["op"]] += remain
                        op_oc_stall[ocs][row["op"]] += int(float(row["stall"] or 0))
                    if row["op"] == "LOAD_OP":
                        load_remain[row["case"]][ocs] += remain

        count_csv = config_dir / "confluence" / "case_op_remain_cycles.csv"
        if count_csv.exists():
            with open(count_csv, newline="") as f:
                for row in csv.DictReader(f):
                    if row["stage"] == "TOTAL":
                        op_counts[row["case"]][ocs][row["op"]] = int(float(row["count"] or 0))

        for log_path in config_dir.glob("*/*.log"):
            cycle = read_gpu_tot_sim_cycle(log_path)
            if cycle is not None:
                total_cycles[log_path.parent.name][ocs] = cycle

    return stage_remain, load_remain, op_counts, op_oc_remain, op_oc_stall, total_cycles


def load_share(stage_remain, load_remain, case, ocs):
    total = sum(stage_remain[case][ocs][stage] for stage in ACTIVE_STAGES)
    return percent(load_remain[case].get(ocs, 0), total)


def load_inst_share(op_counts, case, ocs):
    total = sum(op_counts[case][ocs].values())
    return percent(op_counts[case][ocs].get("LOAD_OP", 0), total)


def plot_op_oc_remain_share(op_oc_remain, output_path):
    plt = load_pyplot()
    ocs_values = sorted(op_oc_remain)
    if not ocs_values:
        return

    op_order = sorted(
        {op for values in op_oc_remain.values() for op in values},
        key=lambda op: sum(op_oc_remain[ocs].get(op, 0) for ocs in ocs_values),
        reverse=True,
    )
    colors = plt.get_cmap("tab20").colors

    fig, ax = plt.subplots(figsize=(16, 8), constrained_layout=True)
    bottoms = [0.0] * len(ocs_values)
    totals = [sum(op_oc_remain[ocs].values()) for ocs in ocs_values]

    for idx, op in enumerate(op_order):
        raw_values = [op_oc_remain[ocs].get(op, 0) for ocs in ocs_values]
        ratios = [percent(value, total) for value, total in zip(raw_values, totals)]
        bars = ax.bar(ocs_values, ratios, bottom=bottoms, label=op, color=colors[idx % len(colors)], width=0.72)
        for bar, ratio, raw in zip(bars, ratios, raw_values):
            if ratio >= 8:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_y() + bar.get_height() / 2,
                    f"{ratio:.0f}%\n{raw/1_000_000:.1f}M",
                    ha="center",
                    va="center",
                    fontsize=7,
                )
            elif ratio >= 4:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_y() + bar.get_height() / 2,
                    f"{ratio:.0f}%",
                    ha="center",
                    va="center",
                    fontsize=7,
                )
        bottoms = [bottoms[i] + ratios[i] for i in range(len(ratios))]

    for x, total in zip(ocs_values, totals):
        ax.text(x, 101.5, f"Σ={total/1_000_000:.1f}M", ha="center", va="bottom", fontsize=8)

    ax.set_title("OCS sweep: operand collector/RFC cycles share by op")
    ax.set_xlabel("ocs / RFC count")
    ax.set_ylabel("op OC/RFC remain share (%)")
    ax.set_xticks(ocs_values)
    ax.set_ylim(0, 112)
    ax.grid(axis="y", linestyle="--", alpha=0.25)
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=8)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_op_oc_metric_by_op_subplots(op_oc_metric, output_path, metric_name, color):
    plt = load_pyplot()
    ocs_values = sorted(op_oc_metric)
    if not ocs_values:
        return

    op_order = sorted(
        {op for values in op_oc_metric.values() for op in values},
        key=lambda op: sum(op_oc_metric[ocs].get(op, 0) for ocs in ocs_values),
        reverse=True,
    )
    ncols = 2
    nrows = (len(op_order) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(18, max(8, nrows * 4.0)), squeeze=False, constrained_layout=True)

    for idx, op in enumerate(op_order):
        ax = axes[idx // ncols][idx % ncols]
        values = [op_oc_metric[ocs].get(op, 0) for ocs in ocs_values]
        values_m = [value / 1_000_000 for value in values]
        bars = ax.bar(ocs_values, values_m, color=color, width=0.72)

        baseline = values[0] if values and values[0] else None
        for bar, value in zip(bars, values):
            if baseline:
                ratio = value / baseline
                label = f"{value/1_000_000:.2f}M\n{ratio:.2f}x"
            else:
                label = f"{value/1_000_000:.2f}M"
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + (max(values_m) * 0.02 if values_m else 0),
                label,
                ha="center",
                va="bottom",
                fontsize=7,
            )

        ax.set_title(op, fontsize=10, fontweight="bold")
        ax.set_xlabel("ocs / RFC count")
        ax.set_ylabel(f"OC/RFC {metric_name} cycles (M)")
        ax.set_xticks(ocs_values)
        ax.set_ylim(0, max(values_m) * 1.22 if values_m and max(values_m) > 0 else 1)
        ax.grid(axis="y", linestyle="--", alpha=0.25)

    for idx in range(len(op_order), nrows * ncols):
        axes[idx // ncols][idx % ncols].axis("off")

    fig.suptitle(f"OCS sweep: OC/RFC {metric_name} cycles by op", fontsize=14)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_case_stage_over_cycle(stage_remain, load_remain, op_counts, total_cycles, output_path, baseline, sort_by):
    plt = load_pyplot()
    cases = [case for case in stage_remain if case in total_cycles]
    if not cases:
        raise SystemExit("No matching case stage data and log cycle data found.")
    if sort_by == "load_inst_share":
        sort_key = lambda case: load_inst_share(op_counts, case, baseline)
        sort_title = f"LOAD inst share@ocs{baseline}"
    else:
        sort_key = lambda case: load_share(stage_remain, load_remain, case, baseline)
        sort_title = f"LOAD remain share@ocs{baseline}"
    cases = sorted(cases, key=sort_key, reverse=True)

    fig_height = max(16, len(cases) * 4.2)
    fig = plt.figure(figsize=(22, fig_height), constrained_layout=True)
    grid = fig.add_gridspec(len(cases), 2, width_ratios=[3.2, 2.0])
    legend_handles = None
    legend_labels = None

    for row, case in enumerate(cases):
        ax_stage = fig.add_subplot(grid[row, 0])
        ax_cycle = fig.add_subplot(grid[row, 1])
        ocs_values = sorted(set(stage_remain[case]) & set(total_cycles[case]))
        if not ocs_values:
            continue

        bottoms = [0.0] * len(ocs_values)
        stage_totals = [sum(stage_remain[case][ocs][stage] for stage in ACTIVE_STAGES) for ocs in ocs_values]

        for stage in ACTIVE_STAGES:
            raw_values = [stage_remain[case][ocs][stage] for ocs in ocs_values]
            ratios = [percent(value, total) for value, total in zip(raw_values, stage_totals)]
            bars = ax_stage.bar(
                ocs_values,
                ratios,
                bottom=bottoms,
                label=stage,
                color=STAGE_COLORS.get(stage),
                width=0.72,
            )

            for bar, ratio, raw in zip(bars, ratios, raw_values):
                if ratio >= 10:
                    ax_stage.text(
                        bar.get_x() + bar.get_width() / 2,
                        bar.get_y() + bar.get_height() / 2,
                        f"{ratio:.0f}%\n{raw/1_000_000:.1f}M",
                        ha="center",
                        va="center",
                        fontsize=6.5,
                    )
                elif ratio >= 4:
                    ax_stage.text(
                        bar.get_x() + bar.get_width() / 2,
                        bar.get_y() + bar.get_height() / 2,
                        f"{ratio:.0f}%",
                        ha="center",
                        va="center",
                        fontsize=6.5,
                    )

            bottoms = [bottoms[i] + ratios[i] for i in range(len(ratios))]

        for x, total in zip(ocs_values, stage_totals):
            ax_stage.text(x, 101.5, f"Σ={total/1_000_000:.1f}M", ha="center", va="bottom", fontsize=7)

        base_cycle = total_cycles[case].get(baseline)
        cycle_values = [total_cycles[case][ocs] for ocs in ocs_values]
        cycle_millions = [value / 1_000_000 for value in cycle_values]
        colors = ["#9ecae1" if ocs != baseline else "#3182bd" for ocs in ocs_values]
        bars = ax_cycle.bar(ocs_values, cycle_millions, color=colors, width=0.72)

        for bar, ocs, cycle in zip(bars, ocs_values, cycle_values):
            if base_cycle:
                delta = (cycle / base_cycle - 1) * 100
                label = f"{cycle/1_000_000:.2f}M\n{delta:+.1f}%"
            else:
                label = f"{cycle/1_000_000:.2f}M"
            ax_cycle.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(cycle_millions) * 0.015,
                label,
                ha="center",
                va="bottom",
                fontsize=7,
            )

        if base_cycle:
            ax_cycle.axhline(base_cycle / 1_000_000, color="black", linestyle="--", linewidth=0.8, alpha=0.5)
            ax_cycle.set_title(f"total cycle, baseline=ocs{baseline}", fontsize=9)
        else:
            ax_cycle.set_title("total cycle", fontsize=9)

        baseline_load_share = load_share(stage_remain, load_remain, case, baseline)
        baseline_load_inst_share = load_inst_share(op_counts, case, baseline)
        ax_stage.set_title(
            f"{short_case_name(case)}  |  LOAD remain@ocs{baseline}={baseline_load_share:.1f}%  |  LOAD inst@ocs{baseline}={baseline_load_inst_share:.1f}%",
            loc="left",
            fontsize=10,
            fontweight="bold",
        )
        ax_stage.set_ylabel("stage remain share (%)", fontsize=8)
        ax_stage.set_ylim(0, 112)
        ax_stage.set_xticks(ocs_values)
        ax_stage.grid(axis="y", linestyle="--", alpha=0.25)
        ax_stage.tick_params(axis="both", labelsize=8)

        ax_cycle.set_ylabel("gpu_tot_sim_cycle (M)", fontsize=8)
        ax_cycle.set_xticks(ocs_values)
        ax_cycle.grid(axis="y", linestyle="--", alpha=0.25)
        ax_cycle.tick_params(axis="both", labelsize=8)
        ax_cycle.set_ylim(0, max(cycle_millions) * 1.18 if cycle_millions else 1)

        if legend_handles is None:
            legend_handles, legend_labels = ax_stage.get_legend_handles_labels()

    if legend_handles:
        fig.legend(legend_handles, legend_labels, loc="upper center", ncol=len(ACTIVE_STAGES), fontsize=9)

    fig.suptitle(
        f"OCS sweep per case: stage remain share and total cycle comparison, sorted by {sort_title}",
        fontsize=14,
    )
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Plot OCS sweep stage remain over total simulation cycles.")
    parser.add_argument("path", nargs="?", help="sweep result directory or its confluence directory; overrides result_path")
    parser.add_argument("--baseline-ocs", type=int, default=baseline_ocs, help="baseline ocs for total cycle comparison")
    parser.add_argument("--output-dir", help="directory for generated png files; default uses sweep confluence directory")
    args = parser.parse_args()

    selected_path = args.path or result_path
    if not selected_path:
        raise SystemExit("Please set result_path at the top of this script, or pass a sweep result path.")

    result_root = resolve_result_root(selected_path)
    output_dir = Path(args.output_dir) if args.output_dir else result_root / "confluence"
    output_dir.mkdir(parents=True, exist_ok=True)

    stage_remain, load_remain, op_counts, op_oc_remain, op_oc_stall, total_cycles = collect_sweep_data(result_root)
    outputs = [
        ("load_remain_share", output_dir / f"ocs_sweep_case_stage_share_sort_by_load_remain_baseline_ocs{args.baseline_ocs}.png"),
        ("load_inst_share", output_dir / f"ocs_sweep_case_stage_share_sort_by_load_inst_baseline_ocs{args.baseline_ocs}.png"),
    ]
    for sort_by, output_path in outputs:
        plot_case_stage_over_cycle(stage_remain, load_remain, op_counts, total_cycles, output_path, args.baseline_ocs, sort_by)
        print(f"plot written to {output_path}")

    op_oc_output_path = output_dir / "ocs_sweep_op_oc_remain_share.png"
    plot_op_oc_remain_share(op_oc_remain, op_oc_output_path)
    print(f"plot written to {op_oc_output_path}")

    op_oc_remain_subplots_output_path = output_dir / "ocs_sweep_op_oc_remain_by_op_subplots.png"
    plot_op_oc_metric_by_op_subplots(op_oc_remain, op_oc_remain_subplots_output_path, "remain", "#f58518")
    print(f"plot written to {op_oc_remain_subplots_output_path}")

    op_oc_stall_subplots_output_path = output_dir / "ocs_sweep_op_oc_stall_by_op_subplots.png"
    plot_op_oc_metric_by_op_subplots(op_oc_stall, op_oc_stall_subplots_output_path, "stall", "#e45756")
    print(f"plot written to {op_oc_stall_subplots_output_path}")


if __name__ == "__main__":
    main()

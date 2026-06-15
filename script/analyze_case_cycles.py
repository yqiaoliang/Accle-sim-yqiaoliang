#!/usr/bin/env python3

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

result_path = "/Users/bytedance/Desktop/Accel-sim/accel-sim-framework/regress_result/20260615_074224"

def resolve_result_dir(value):
    path = Path(value)
    if path.exists():
        return path.resolve()
    script_dir = Path(__file__).resolve().parent
    regress_result_path = script_dir.parent / "regress_result" / value
    if regress_result_path.exists():
        return regress_result_path.resolve()
    return path.resolve()


def short_case_label(name):
    return str(name).split("-", 1)[0]


def load_pyplot():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def parse_last_gpu_cycle(log_path):
    pattern = re.compile(r"gpu_tot_sim_cycle\s*=\s*(\d+)")
    last_value = None
    with open(log_path, "r", errors="ignore") as f:
        for line in f:
            match = pattern.search(line)
            if match:
                last_value = int(match.group(1))
    return last_value


def parse_inst_stage_op_counts(log_path):
    pattern = re.compile(r"\bop:\s*([^\s,]+)")
    counts = Counter()
    with open(log_path, "r", errors="ignore") as f:
        for line in f:
            match = pattern.search(line)
            if match:
                counts[match.group(1)] += 1
    return counts



def find_case_logs(root):
    records = []
    for log_path in sorted(root.rglob("*.log")):
        if log_path.name == "inst_stage.log":
            continue
        case_dir = log_path.parent
        config_dir = case_dir.parent
        if config_dir == root or config_dir.name == "confluence":
            continue
        cycles = parse_last_gpu_cycle(log_path)
        if cycles is None:
            continue
        records.append({
            "config": config_dir.name,
            "case": case_dir.name,
            "case_label": short_case_label(case_dir.name),
            "cycles": cycles,
            "log_path": log_path,
        })
    return records


def write_config_csv(root, records):
    by_config = defaultdict(list)
    for record in records:
        by_config[record["config"]].append(record)

    for config, config_records in by_config.items():
        confluence_dir = root / config / "confluence"
        confluence_dir.mkdir(exist_ok=True)
        csv_path = confluence_dir / "case_gpu_tot_sim_cycle.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["case", "case_label", "gpu_tot_sim_cycle", "log_path"])
            for record in sorted(config_records, key=lambda item: item["case"]):
                writer.writerow([record["case"], record["case_label"], record["cycles"], record["log_path"]])


def write_root_csv(root, records):
    confluence_dir = root / "confluence"
    confluence_dir.mkdir(exist_ok=True)
    csv_path = confluence_dir / "config_case_gpu_tot_sim_cycle.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["case", "case_label", "config", "gpu_tot_sim_cycle", "log_path"])
        for record in sorted(records, key=lambda item: (item["case_label"], item["case"], item["config"])):
            writer.writerow([record["case"], record["case_label"], record["config"], record["cycles"], record["log_path"]])
    return csv_path


def write_case_op_count_csv(root, records):
    confluence_dir = root / "confluence"
    confluence_dir.mkdir(exist_ok=True)
    csv_path = confluence_dir / "case_op_count.csv"
    by_case = {}
    for record in sorted(records, key=lambda item: (item["case_label"], item["case"], item["config"])):
        by_case.setdefault(record["case"], record)

    rows = []
    for record in by_case.values():
        inst_stage_path = record["log_path"].parent / "inst_stage.log"
        if not inst_stage_path.exists():
            continue
        counts = parse_inst_stage_op_counts(inst_stage_path)
        total = sum(counts.values())
        if not total:
            continue
        for op, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
            rows.append({
                "case": record["case"],
                "case_label": record["case_label"],
                "op": op,
                "count": count,
                "percent": count / total * 100,
                "total_instructions": total,
                "source_config": record["config"],
                "inst_stage_log_path": inst_stage_path,
            })

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["case", "case_label", "op", "count", "percent", "total_instructions", "source_config", "inst_stage_log_path"])
        for row in sorted(rows, key=lambda item: (item["case_label"], item["case"], -item["count"], item["op"])):
            writer.writerow([
                row["case"],
                row["case_label"],
                row["op"],
                row["count"],
                f"{row['percent']:.6f}",
                row["total_instructions"],
                row["source_config"],
                row["inst_stage_log_path"],
            ])
    return csv_path, len(by_case), len(rows)



def add_horizontal_value_labels(ax, bars, fmt="{:.0f}"):
    for bar in bars:
        width = bar.get_width()
        if width == 0:
            continue
        offset = 4 if width > 0 else -4
        ha = "left" if width > 0 else "right"
        ax.annotate(fmt.format(width),
                    xy=(width, bar.get_y() + bar.get_height() / 2),
                    xytext=(offset, 0),
                    textcoords="offset points",
                    ha=ha, va="center", fontsize=8)


def add_row_guides(ax, y_pos):
    for idx, y in enumerate(y_pos):
        if idx % 2 == 0:
            ax.axhspan(y - 0.5, y + 0.5, color="#f2f2f2", alpha=0.55, zorder=0)
        ax.axhline(y + 0.5, color="#d9d9d9", linewidth=0.6, zorder=1)
    ax.grid(axis="x", linestyle="--", alpha=0.35)
    ax.set_axisbelow(True)


def is_lrr_rfc0_ocu8_config(config):
    return "sched_lrr" in config and "rfc0" in config and "ocu8" in config


def group_records_by_case(records):
    by_case = defaultdict(list)
    for record in records:
        by_case[record["case_label"]].append(record)
    return by_case


def plot_root_case_cycles(root, records):
    plt = load_pyplot()
    by_case = group_records_by_case(records)

    cases = sorted(by_case.keys())
    if not cases:
        return None

    fig_height = max(5, len(cases) * 3.4)
    fig, axes = plt.subplots(len(cases), 1, figsize=(18, fig_height), squeeze=False, constrained_layout=True)
    for ax, case_label in zip(axes[:, 0], cases):
        case_records = sorted(by_case[case_label], key=lambda item: item["config"])
        labels = [record["config"] for record in case_records]
        values = [record["cycles"] for record in case_records]
        y_pos = list(range(len(labels)))
        add_row_guides(ax, y_pos)
        bars = ax.barh(y_pos, values, zorder=2)
        add_horizontal_value_labels(ax, bars)
        ax.set_title(case_label)
        ax.set_xlabel("gpu_tot_sim_cycle")
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels)

    fig.suptitle("gpu_tot_sim_cycle by case across configs")
    output_path = root / "confluence" / "case_gpu_tot_sim_cycle_by_config.png"
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return output_path



def plot_relative_case_cycles(root, records, baseline_mode):
    plt = load_pyplot()
    by_case = group_records_by_case(records)
    cases = sorted(by_case.keys())
    if not cases:
        return None

    fig_height = max(5, len(cases) * 3.4)
    fig, axes = plt.subplots(len(cases), 1, figsize=(18, fig_height), squeeze=False, constrained_layout=True)
    missing_baseline_cases = []
    for ax, case_label in zip(axes[:, 0], cases):
        case_records = sorted(by_case[case_label], key=lambda item: item["config"])
        if baseline_mode == "lrr_rfc0_ocu8":
            baseline_records = [record for record in case_records if is_lrr_rfc0_ocu8_config(record["config"])]
            if not baseline_records:
                missing_baseline_cases.append(case_label)
                ax.set_title(f"{case_label} (missing lrr/rfc0/ocu8 baseline)")
                ax.axis("off")
                continue
            baseline_record = baseline_records[0]
            baseline = baseline_record["cycles"]
            title = f"{case_label}: relative to lrr/rfc0/ocu8"
        else:
            baseline_record = min(case_records, key=lambda record: record["cycles"])
            baseline = baseline_record["cycles"]
            title = f"{case_label}: relative to best config"

        labels = []
        values = []
        baseline_indices = []
        for idx, record in enumerate(case_records):
            is_baseline = record is baseline_record
            labels.append(record["config"] + ("  [BASE]" if is_baseline else ""))
            values.append((record["cycles"] - baseline) / baseline * 100)
            if is_baseline:
                baseline_indices.append(idx)
        y_pos = list(range(len(labels)))
        add_row_guides(ax, y_pos)
        colors = ["#1f77b4" if idx in baseline_indices else ("#d62728" if value >= 0 else "#2ca02c") for idx, value in enumerate(values)]
        bars = ax.barh(y_pos, values, color=colors, zorder=2)
        add_horizontal_value_labels(ax, bars, "{:+.1f}%")
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_title(title)
        ax.set_xlabel("cycle change vs baseline (%)")
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels)
        for idx, tick in enumerate(ax.get_yticklabels()):
            if idx in baseline_indices:
                tick.set_fontweight("bold")
                tick.set_color("#1f77b4")

    if baseline_mode == "lrr_rfc0_ocu8":
        name = "case_gpu_tot_sim_cycle_relative_to_lrr_rfc0_ocu8.png"
        fig.suptitle("gpu_tot_sim_cycle change relative to lrr/rfc0/ocu8")
    else:
        name = "case_gpu_tot_sim_cycle_relative_to_best.png"
        fig.suptitle("gpu_tot_sim_cycle change relative to best config per case")
    output_path = root / "confluence" / name
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return output_path, missing_baseline_cases


def main(selected_result_path, no_graphs=False):
    root = resolve_result_dir(selected_result_path)
    if not root.exists():
        raise SystemExit(f"Result directory does not exist: {root}")

    records = find_case_logs(root)
    if not records:
        raise SystemExit(f"No case .log with gpu_tot_sim_cycle found under: {root}")

    write_config_csv(root, records)
    root_csv = write_root_csv(root, records)
    print(f"Wrote root CSV: {root_csv}")
    op_count_csv, case_count, op_row_count = write_case_op_count_csv(root, records)
    print(f"Wrote case op count CSV: {op_count_csv} ({case_count} case(s), {op_row_count} row(s))")
    if not no_graphs:
        try:
            output_path = plot_root_case_cycles(root, records)
            if output_path:
                print(f"Wrote root graph: {output_path}")
            lrr_output, missing_cases = plot_relative_case_cycles(root, records, "lrr_rfc0_ocu8")
            if lrr_output:
                print(f"Wrote relative graph: {lrr_output}")
            if missing_cases:
                print("Missing lrr/rfc0/ocu8 baseline for: " + ", ".join(missing_cases))
            best_output, _ = plot_relative_case_cycles(root, records, "best")
            if best_output:
                print(f"Wrote relative graph: {best_output}")
        except ImportError as exc:
            print(f"matplotlib is unavailable ({exc}); CSV files were still written")

    print(f"Processed {len(records)} case log(s)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze final gpu_tot_sim_cycle values from case result logs.")
    parser.add_argument("result_dir", nargs="?",
                        help="Completed result directory to scan. Overrides result_path when provided.")
    parser.add_argument("--no-graphs", action="store_true",
                        help="Only write CSV files; skip PNG generation.")
    args = parser.parse_args()
    selected_result_path = args.result_dir or result_path
    if not selected_result_path:
        parser.error("set result_path in this script or pass result_dir on the command line")
    main(selected_result_path, args.no_graphs)

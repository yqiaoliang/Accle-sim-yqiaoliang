#!/usr/bin/env python3

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

result_path = "/Users/bytedance/Desktop/Accel-sim/accel-sim-framework/regress_result/20260615_074224"

STALL_REASONS = [
    "RFC_NUM_CONFLICT",
    "BANK_CONFLICT",
    "EXEC_NUM_CONFLICT",
]
STALL_COLORS = {
    "RFC_NUM_CONFLICT": "#1f77b4",
    "BANK_CONFLICT": "#ff7f0e",
    "EXEC_NUM_CONFLICT": "#2ca02c",
}
FALLBACK_COLORS = ["#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]


def resolve_result_dir(value):
    path = Path(value)
    if path.exists():
        return path.resolve()
    script_dir = Path(__file__).resolve().parent
    candidate = (script_dir / value).resolve()
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"result dir not found: {value}")


def load_pyplot():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def short_case_label(case_dir_name):
    suffixes = [
        "-rodinia-2.0-ft",
        "-rodinia-3.1",
        "-cuda-11.0",
    ]
    name = case_dir_name
    for suffix in suffixes:
        if suffix in name:
            name = name.split(suffix)[0]
            break
    return name


def config_sort_key(config_name):
    values = []
    for key in ["rfc", "bank", "wbd", "reuse", "ocs", "regb", "ocu", "dp"]:
        match = re.search(rf"(?:^|_){key}(\d+)", config_name)
        values.append(int(match.group(1)) if match else -1)
    return tuple(values) + (config_name,)


def find_case_dirs(root):
    dirs = []
    for config_dir in sorted(root.iterdir()):
        if not config_dir.is_dir() or config_dir.name == "confluence":
            continue
        for case_dir in sorted(config_dir.iterdir()):
            log_path = case_dir / "inst_stage.log"
            if case_dir.is_dir() and log_path.exists():
                dirs.append((config_dir.name, case_dir.name, log_path))
    return dirs


def parse_inst_stage_log(log_path):
    header_pattern = re.compile(r"warp_id:\s*\d+,\s*pc:\s*0x[0-9a-fA-F]+,\s*op:\s*(\S+)")
    stall_pattern = re.compile(r"^\s*([A-Z0-9_]+)\s*:\s*oc_stall=\s*(\d+)")
    current_op = None
    case_stalls = Counter()
    op_stalls = defaultdict(Counter)

    with open(log_path, "r", errors="ignore") as f:
        for line in f:
            header = header_pattern.search(line)
            if header:
                current_op = header.group(1)
                continue
            stall = stall_pattern.search(line)
            if stall and current_op is not None:
                reason = stall.group(1)
                value = int(stall.group(2))
                case_stalls[reason] += value
                op_stalls[current_op][reason] += value
    return case_stalls, op_stalls


def collect_records(root):
    records = []
    config_op_stalls = defaultdict(lambda: defaultdict(Counter))
    all_reasons = list(STALL_REASONS)
    seen_reasons = set(all_reasons)
    for config, case, log_path in find_case_dirs(root):
        case_stalls, op_stalls = parse_inst_stage_log(log_path)
        for reason in case_stalls:
            if reason not in seen_reasons:
                all_reasons.append(reason)
                seen_reasons.add(reason)
        for op, stalls in op_stalls.items():
            config_op_stalls[config][op].update(stalls)
            for reason in stalls:
                if reason not in seen_reasons:
                    all_reasons.append(reason)
                    seen_reasons.add(reason)
        records.append({
            "config": config,
            "case": case,
            "case_label": short_case_label(case),
            "log_path": log_path,
            "case_stalls": case_stalls,
            "op_stalls": op_stalls,
        })
    return records, config_op_stalls, all_reasons


def reason_colors(reasons):
    colors = []
    for idx, reason in enumerate(reasons):
        colors.append(STALL_COLORS.get(reason, FALLBACK_COLORS[idx % len(FALLBACK_COLORS)]))
    return colors


def global_op_order(records):
    totals = Counter()
    for record in records:
        for op, stalls in record["op_stalls"].items():
            totals[op] += sum(stalls.values())
    return [op for op, _ in sorted(totals.items(), key=lambda item: (-item[1], item[0]))]


def write_case_config_csv(root, records, reasons):
    output_path = root / "confluence" / "oc_stall_by_case_config.csv"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["case", "case_label", "config", "stall_reason", "oc_stall", "percent", "total_oc_stall", "inst_stage_log_path"])
        for record in sorted(records, key=lambda item: (item["case_label"], config_sort_key(item["config"]))):
            total = sum(record["case_stalls"].values())
            for reason in reasons:
                value = record["case_stalls"].get(reason, 0)
                percent = value / total * 100 if total else 0
                writer.writerow([record["case"], record["case_label"], record["config"], reason, value, f"{percent:.6f}", total, record["log_path"]])
    return output_path


def write_case_config_op_csv(root, records, reasons):
    output_path = root / "confluence" / "oc_stall_by_case_config_op.csv"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["case", "case_label", "config", "op", "stall_reason", "oc_stall", "percent", "total_op_oc_stall", "inst_stage_log_path"])
        for record in sorted(records, key=lambda item: (item["case_label"], config_sort_key(item["config"]))):
            for op in sorted(record["op_stalls"]):
                stalls = record["op_stalls"][op]
                total = sum(stalls.values())
                for reason in reasons:
                    value = stalls.get(reason, 0)
                    percent = value / total * 100 if total else 0
                    writer.writerow([record["case"], record["case_label"], record["config"], op, reason, value, f"{percent:.6f}", total, record["log_path"]])
    return output_path


def write_config_op_csv(root, config_op_stalls, reasons):
    output_path = root / "confluence" / "oc_stall_by_config_op.csv"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["config", "op", "stall_reason", "oc_stall", "percent", "total_op_oc_stall"])
        for config in sorted(config_op_stalls, key=config_sort_key):
            for op in sorted(config_op_stalls[config]):
                stalls = config_op_stalls[config][op]
                total = sum(stalls.values())
                for reason in reasons:
                    value = stalls.get(reason, 0)
                    percent = value / total * 100 if total else 0
                    writer.writerow([config, op, reason, value, f"{percent:.6f}", total])
    return output_path


def annotate_segments(ax, bars, values, totals, normalize):
    for bar, value, total in zip(bars, values, totals):
        if value <= 0:
            continue
        width = bar.get_width()
        if width <= 0:
            continue
        label = f"{int(value)}\n{value / total * 100:.1f}%" if total else "0\n0.0%"
        if normalize:
            label = f"{int(value)}\n{width:.1f}%"
        if width >= (6 if normalize else max(total * 0.06, 1)):
            ax.text(bar.get_x() + width / 2, bar.get_y() + bar.get_height() / 2, label,
                    ha="center", va="center", fontsize=7, color="white")


def plot_case_config_stalls(root, records, reasons):
    plt = load_pyplot()
    output_path = root / "confluence" / "oc_stall_case_config_cycles.png"
    cases = sorted({record["case_label"] for record in records})
    records_by_case = defaultdict(list)
    for record in records:
        records_by_case[record["case_label"]].append(record)

    fig_height = max(5, len(cases) * 3.8)
    fig, axes = plt.subplots(len(cases), 1, figsize=(22, fig_height), squeeze=False, constrained_layout=True)
    colors = reason_colors(reasons)
    for ax, case_label in zip(axes[:, 0], cases):
        case_records = sorted(records_by_case[case_label], key=lambda item: config_sort_key(item["config"]))
        labels = [record["config"] for record in case_records]
        y_pos = list(range(len(labels)))
        left = [0.0] * len(labels)
        totals = [sum(record["case_stalls"].values()) for record in case_records]
        for idx in y_pos:
            ax.axhline(idx, color="#eeeeee", linewidth=0.6, zorder=0)
        for reason, color in zip(reasons, colors):
            raw_values = [record["case_stalls"].get(reason, 0) for record in case_records]
            bars = ax.barh(y_pos, raw_values, left=left, label=reason, color=color, zorder=2)
            annotate_segments(ax, bars, raw_values, totals, normalize=False)
            left = [base + value for base, value in zip(left, raw_values)]
        ax.set_title(case_label)
        ax.set_xlabel("OC stall cycles")
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels)
        ax.legend(loc="lower right")
    fig.suptitle("OC stall cycles by case and config")
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return output_path


def plot_case_config_op_stalls(root, records, reasons, op_order):
    plt = load_pyplot()
    output_path = root / "confluence" / "oc_stall_case_config_op_cycles.png"
    panels = []
    for record in sorted(records, key=lambda item: (item["case_label"], config_sort_key(item["config"]))):
        ops = [op for op in op_order if sum(record["op_stalls"].get(op, {}).values()) > 0]
        if ops:
            panels.append((record, ops))
    if not panels:
        return None

    fig_height = max(8, len(panels) * 2.8)
    fig, axes = plt.subplots(len(panels), 1, figsize=(24, fig_height), squeeze=False, constrained_layout=True)
    colors = reason_colors(reasons)
    for ax, (record, ops) in zip(axes[:, 0], panels):
        y_pos = list(range(len(ops)))
        left = [0.0] * len(ops)
        totals = [sum(record["op_stalls"][op].values()) for op in ops]
        for idx in y_pos:
            ax.axhline(idx, color="#eeeeee", linewidth=0.6, zorder=0)
        for reason, color in zip(reasons, colors):
            raw_values = [record["op_stalls"][op].get(reason, 0) for op in ops]
            bars = ax.barh(y_pos, raw_values, left=left, label=reason, color=color, zorder=2)
            annotate_segments(ax, bars, raw_values, totals, normalize=False)
            left = [base + value for base, value in zip(left, raw_values)]
        ax.set_title(f"{record['case_label']} | {record['config']}")
        ax.set_xlabel("OC stall cycles")
        ax.set_yticks(y_pos)
        ax.set_yticklabels(ops)
        ax.legend(loc="lower right")
    fig.suptitle("OC stall cycles by op for each case/config")
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def plot_config_op_stalls(root, config_op_stalls, reasons, op_order):
    plt = load_pyplot()
    output_path = root / "confluence" / "oc_stall_config_op_cycles.png"
    configs = sorted(config_op_stalls, key=config_sort_key)
    configs = [config for config in configs if any(sum(stalls.values()) > 0 for stalls in config_op_stalls[config].values())]
    if not configs:
        return None

    fig_height = max(5, len(configs) * 3.4)
    fig, axes = plt.subplots(len(configs), 1, figsize=(22, fig_height), squeeze=False, constrained_layout=True)
    colors = reason_colors(reasons)
    for ax, config in zip(axes[:, 0], configs):
        ops = [op for op in op_order if sum(config_op_stalls[config].get(op, {}).values()) > 0]
        y_pos = list(range(len(ops)))
        left = [0.0] * len(ops)
        totals = [sum(config_op_stalls[config][op].values()) for op in ops]
        for idx in y_pos:
            ax.axhline(idx, color="#eeeeee", linewidth=0.6, zorder=0)
        for reason, color in zip(reasons, colors):
            raw_values = [config_op_stalls[config][op].get(reason, 0) for op in ops]
            bars = ax.barh(y_pos, raw_values, left=left, label=reason, color=color, zorder=2)
            annotate_segments(ax, bars, raw_values, totals, normalize=False)
            left = [base + value for base, value in zip(left, raw_values)]
        ax.set_title(config)
        ax.set_xlabel("OC stall cycles")
        ax.set_yticks(y_pos)
        ax.set_yticklabels(ops)
        ax.legend(loc="lower right")
    fig.suptitle("OC stall cycles by op, summed across all cases in each config")
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return output_path


def plot_op_grouped_case_config_stalls(root, records, reasons, op_order):
    plt = load_pyplot()
    output_path = root / "confluence" / "oc_stall_op_grouped_case_config_cycles.png"
    records_by_op = defaultdict(list)
    for record in records:
        for op, stalls in record["op_stalls"].items():
            if sum(stalls.values()) > 0:
                records_by_op[op].append(record)

    ops = [op for op in op_order if records_by_op.get(op)]
    if not ops:
        return None

    total_rows = sum(len(records_by_op[op]) for op in ops)
    fig_height = max(8, len(ops) * 1.2 + total_rows * 0.38)
    fig, axes = plt.subplots(len(ops), 1, figsize=(30, fig_height), squeeze=False, constrained_layout=True)
    colors = reason_colors(reasons)
    for ax, op in zip(axes[:, 0], ops):
        op_records = sorted(records_by_op[op], key=lambda item: (item["case_label"], config_sort_key(item["config"])))
        labels = [f"{record['case_label']} | {record['config']}" for record in op_records]
        y_pos = list(range(len(labels)))
        left = [0.0] * len(labels)
        totals = [sum(record["op_stalls"][op].values()) for record in op_records]
        for idx in y_pos:
            ax.axhline(idx, color="#eeeeee", linewidth=0.6, zorder=0)
        for reason, color in zip(reasons, colors):
            raw_values = [record["op_stalls"][op].get(reason, 0) for record in op_records]
            bars = ax.barh(y_pos, raw_values, left=left, label=reason, color=color, zorder=2)
            annotate_segments(ax, bars, raw_values, totals, normalize=False)
            left = [base + value for base, value in zip(left, raw_values)]
        ax.set_title(op)
        ax.set_xlabel("OC stall cycles")
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels)
        ax.legend(loc="lower right")
    fig.suptitle("OC stall cycles grouped by op, comparing case/config")
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def safe_filename(name):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "case"


def plot_op_grouped_case_config_stalls_by_case(root, records, reasons, op_order):
    plt = load_pyplot()
    output_dir = root / "confluence" / "oc_stall_op_grouped_case_config_cycles_by_case"
    output_dir.mkdir(exist_ok=True)
    records_by_case = defaultdict(list)
    for record in records:
        records_by_case[record["case_label"]].append(record)

    colors = reason_colors(reasons)
    output_paths = []
    for case_label in sorted(records_by_case):
        case_records = records_by_case[case_label]
        ops = [op for op in op_order if any(sum(record["op_stalls"].get(op, {}).values()) > 0 for record in case_records)]
        if not ops:
            continue
        total_rows = sum(
            1 for op in ops for record in case_records
            if sum(record["op_stalls"].get(op, {}).values()) > 0
        )
        fig_height = max(6, len(ops) * 1.2 + total_rows * 0.42)
        fig, axes = plt.subplots(len(ops), 1, figsize=(28, fig_height), squeeze=False, constrained_layout=True)
        for ax, op in zip(axes[:, 0], ops):
            op_records = sorted(
                [record for record in case_records if sum(record["op_stalls"].get(op, {}).values()) > 0],
                key=lambda item: config_sort_key(item["config"]),
            )
            labels = [record["config"] for record in op_records]
            y_pos = list(range(len(labels)))
            left = [0.0] * len(labels)
            totals = [sum(record["op_stalls"][op].values()) for record in op_records]
            for idx in y_pos:
                ax.axhline(idx, color="#eeeeee", linewidth=0.6, zorder=0)
            for reason, color in zip(reasons, colors):
                raw_values = [record["op_stalls"][op].get(reason, 0) for record in op_records]
                bars = ax.barh(y_pos, raw_values, left=left, label=reason, color=color, zorder=2)
                annotate_segments(ax, bars, raw_values, totals, normalize=False)
                left = [base + value for base, value in zip(left, raw_values)]
            ax.set_title(op)
            ax.set_xlabel("OC stall cycles")
            ax.set_yticks(y_pos)
            ax.set_yticklabels(labels)
            ax.legend(loc="lower right")
        fig.suptitle(f"OC stall cycles grouped by op for {case_label}")
        output_path = output_dir / f"{safe_filename(case_label)}.png"
        fig.savefig(output_path, dpi=160)
        plt.close(fig)
        output_paths.append(output_path)
    return output_paths


def plot_op_case_grouped_config_stalls(root, records, reasons, op_order):
    plt = load_pyplot()
    output_path = root / "confluence" / "oc_stall_op_case_grouped_config_cycles.png"
    records_by_op_case = defaultdict(list)
    for record in records:
        for op, stalls in record["op_stalls"].items():
            if sum(stalls.values()) > 0:
                records_by_op_case[(op, record["case_label"])].append(record)

    case_order = sorted({record["case_label"] for record in records})
    panels = []
    for op in op_order:
        for case_label in case_order:
            op_case_records = records_by_op_case.get((op, case_label), [])
            if op_case_records:
                panels.append((op, case_label, op_case_records))
    if not panels:
        return None

    total_rows = sum(len(panel_records) for _, _, panel_records in panels)
    fig_height = max(8, len(panels) * 0.95 + total_rows * 0.42)
    fig, axes = plt.subplots(len(panels), 1, figsize=(30, fig_height), squeeze=False, constrained_layout=True)
    colors = reason_colors(reasons)
    for ax, (op, case_label, op_case_records) in zip(axes[:, 0], panels):
        op_case_records = sorted(op_case_records, key=lambda item: config_sort_key(item["config"]))
        labels = [record["config"] for record in op_case_records]
        y_pos = list(range(len(labels)))
        left = [0.0] * len(labels)
        totals = [sum(record["op_stalls"][op].values()) for record in op_case_records]
        for idx in y_pos:
            ax.axhline(idx, color="#eeeeee", linewidth=0.6, zorder=0)
        for reason, color in zip(reasons, colors):
            raw_values = [record["op_stalls"][op].get(reason, 0) for record in op_case_records]
            bars = ax.barh(y_pos, raw_values, left=left, label=reason, color=color, zorder=2)
            annotate_segments(ax, bars, raw_values, totals, normalize=False)
            left = [base + value for base, value in zip(left, raw_values)]
        ax.set_title(f"{op} | {case_label}")
        ax.set_xlabel("OC stall cycles")
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels)
        ax.legend(loc="lower right")
    fig.suptitle("OC stall cycles grouped by op and case, comparing configs")
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def plot_op_grouped_config_stalls(root, config_op_stalls, reasons, op_order):
    plt = load_pyplot()
    output_path = root / "confluence" / "oc_stall_op_grouped_config_cycles.png"
    ops = [op for op in op_order if any(sum(config_op_stalls[config].get(op, {}).values()) > 0 for config in config_op_stalls)]
    if not ops:
        return None

    configs = sorted(config_op_stalls, key=config_sort_key)
    fig_height = max(6, len(ops) * 3.6)
    fig, axes = plt.subplots(len(ops), 1, figsize=(24, fig_height), squeeze=False, constrained_layout=True)
    colors = reason_colors(reasons)
    for ax, op in zip(axes[:, 0], ops):
        op_configs = [config for config in configs if sum(config_op_stalls[config].get(op, {}).values()) > 0]
        y_pos = list(range(len(op_configs)))
        left = [0.0] * len(op_configs)
        totals = [sum(config_op_stalls[config][op].values()) for config in op_configs]
        for idx in y_pos:
            ax.axhline(idx, color="#eeeeee", linewidth=0.6, zorder=0)
        for reason, color in zip(reasons, colors):
            raw_values = [config_op_stalls[config][op].get(reason, 0) for config in op_configs]
            bars = ax.barh(y_pos, raw_values, left=left, label=reason, color=color, zorder=2)
            annotate_segments(ax, bars, raw_values, totals, normalize=False)
            left = [base + value for base, value in zip(left, raw_values)]
        ax.set_title(op)
        ax.set_xlabel("OC stall cycles")
        ax.set_yticks(y_pos)
        ax.set_yticklabels(op_configs)
        ax.legend(loc="lower right")
    fig.suptitle("OC stall cycles grouped by op, comparing configs")
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return output_path


def main(selected_result_path, no_graphs=False):
    root = resolve_result_dir(selected_result_path)
    print(f"Scanning: {root}")
    records, config_op_stalls, reasons = collect_records(root)
    if not records:
        print("No inst_stage.log files found")
        return

    confluence_dir = root / "confluence"
    confluence_dir.mkdir(exist_ok=True)
    case_csv = write_case_config_csv(root, records, reasons)
    case_op_csv = write_case_config_op_csv(root, records, reasons)
    config_op_csv = write_config_op_csv(root, config_op_stalls, reasons)
    print(f"Wrote CSV: {case_csv}")
    print(f"Wrote CSV: {case_op_csv}")
    print(f"Wrote CSV: {config_op_csv}")

    if not no_graphs:
        op_order = global_op_order(records)
        case_graph = plot_case_config_stalls(root, records, reasons)
        case_op_graph = plot_case_config_op_stalls(root, records, reasons, op_order)
        config_op_graph = plot_config_op_stalls(root, config_op_stalls, reasons, op_order)
        op_grouped_case_config_graph = plot_op_grouped_case_config_stalls(root, records, reasons, op_order)
        op_grouped_case_graphs = plot_op_grouped_case_config_stalls_by_case(root, records, reasons, op_order)
        op_case_grouped_config_graph = plot_op_case_grouped_config_stalls(root, records, reasons, op_order)
        op_grouped_config_graph = plot_op_grouped_config_stalls(root, config_op_stalls, reasons, op_order)
        print(f"Wrote graph: {case_graph}")
        if case_op_graph:
            print(f"Wrote graph: {case_op_graph}")
        if config_op_graph:
            print(f"Wrote graph: {config_op_graph}")
        if op_grouped_case_config_graph:
            print(f"Wrote graph: {op_grouped_case_config_graph}")
        if op_grouped_case_graphs:
            print(f"Wrote {len(op_grouped_case_graphs)} per-case op-grouped graph(s): {op_grouped_case_graphs[0].parent}")
        if op_case_grouped_config_graph:
            print(f"Wrote graph: {op_case_grouped_config_graph}")
        if op_grouped_config_graph:
            print(f"Wrote graph: {op_grouped_config_graph}")
    print(f"Processed {len(records)} case log(s)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze OC stall reasons from inst_stage.log files.")
    parser.add_argument("result_dir", nargs="?", default=result_path,
                        help="Regression result directory. Defaults to result_path in this script.")
    parser.add_argument("--no-graphs", action="store_true", help="Only write CSV files.")
    args = parser.parse_args()
    main(args.result_dir, args.no_graphs)

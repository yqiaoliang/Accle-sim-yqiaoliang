#!/usr/bin/env python3

import argparse
import csv
import os
import re
import statistics
from collections import defaultdict
from pathlib import Path

result_path = "/Users/bytedance/Desktop/Accel-sim/accel-sim-framework/regress_result/20260615_074224"
bypass_config_name_list = []
bypass_first_config_count = 0

STAGES = ["NONE", "SCHEDULER", "OPERAND_COLLECTOR", "EXECUTION_PIPELINE", "WRITEBACK"]
ACTIVE_STAGES = STAGES[1:]
def parse_inst_stage_log(path):
    current = None
    re_header = re.compile(r"warp_id:\s*(\d+),\s*pc:\s*(0x[0-9a-fA-F]+),\s*op:\s*(\S+)")
    re_issue = re.compile(r"issue_to_operand_collector_cycles:\s*(\d+)")
    re_wb = re.compile(r"writeback_cycles:\s*(\d+)")
    re_stage = re.compile(r"(\S+)\s*:\s*stall=\s*(\d+)\s*remain=\s*(\d+)")

    with open(path, "r", errors="ignore") as f:
        for line in f:
            m = re_header.search(line)
            if m:
                if current is not None:
                    yield current
                current = {
                    "warp_id": int(m.group(1)),
                    "pc": m.group(2),
                    "op": m.group(3),
                    "issue_to_operand_collector_cycles": 0,
                    "writeback_cycles": 0,
                    "stages": {stage: {"stall": 0, "remain": 0} for stage in STAGES},
                }
                continue
            if current is None:
                continue
            m = re_issue.search(line)
            if m:
                current["issue_to_operand_collector_cycles"] = int(m.group(1))
                continue
            m = re_wb.search(line)
            if m:
                current["writeback_cycles"] = int(m.group(1))
                continue
            m = re_stage.search(line)
            if m and m.group(1) in current["stages"]:
                current["stages"][m.group(1)]["stall"] = int(m.group(2))
                current["stages"][m.group(1)]["remain"] = int(m.group(3))

    if current is not None:
        yield current


def update_aggregate(agg, key, record):
    for stage in ACTIVE_STAGES:
        agg[key][stage]["stall"] += record["stages"][stage]["stall"]
        agg[key][stage]["remain"] += record["stages"][stage]["remain"]


def update_op_latency(values, record):
    op = record["op"]
    total = 0
    for stage in ACTIVE_STAGES:
        latency = record["stages"][stage]["remain"]
        values[op][stage].append(latency)
        total += latency
    values[op]["TOTAL"].append(total)


def aggregate_inst_stage_log(path):
    warp_agg = defaultdict(lambda: {stage: {"stall": 0, "remain": 0} for stage in ACTIVE_STAGES})
    op_agg = defaultdict(lambda: {stage: {"stall": 0, "remain": 0} for stage in ACTIVE_STAGES})
    op_latency = defaultdict(lambda: {stage: [] for stage in ACTIVE_STAGES + ["TOTAL"]})
    for record in parse_inst_stage_log(path):
        update_aggregate(warp_agg, record["warp_id"], record)
        update_aggregate(op_agg, record["op"], record)
        update_op_latency(op_latency, record)
    return warp_agg, op_agg, op_latency


def percent(value, total):
    return value / total * 100 if total else 0.0


def safe_name(name):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name)).strip("_") or "case"


def write_case_csv(case_dir, warp_agg, op_agg, op_latency):
    csv_path = case_dir / "inst_stage_result.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        write_metric_table(writer, "STALL TABLE", "stall", warp_agg, op_agg)
        writer.writerow([])
        write_metric_table(writer, "REMAIN TABLE", "remain", warp_agg, op_agg)
        writer.writerow([])
        writer.writerow(["=== OP STAGE LATENCY (remain cycles) ==="])
        header = ["op", "count"]
        for stage in ACTIVE_STAGES:
            header.extend([f"{stage}_avg", f"{stage}_median"])
        header.extend(["TOTAL_avg", "TOTAL_median"])
        writer.writerow(header)
        for op, stage_values in sorted(op_latency.items()):
            row = [op, latency_count(stage_values["TOTAL"])]
            for stage in ACTIVE_STAGES:
                row.extend(latency_avg_median(stage_values[stage]))
            row.extend(latency_avg_median(stage_values["TOTAL"]))
            writer.writerow(row)
    return csv_path


def write_metric_table(writer, title, metric, warp_agg, op_agg):
    writer.writerow([f"=== {title} ==="])
    header = ["category", "key"]
    for stage in ACTIVE_STAGES:
        header.extend([f"{stage}_{metric}", f"{stage}_%"])
    writer.writerow(header)
    write_metric_rows(writer, "warp", warp_agg, metric)
    writer.writerow([])
    write_metric_rows(writer, "op", op_agg, metric)


def write_metric_rows(writer, category, agg, metric):
    totals = {stage: 0 for stage in ACTIVE_STAGES}

    def row_total(item):
        return sum(item[1][stage][metric] for stage in ACTIVE_STAGES)

    for key, data in sorted(agg.items(), key=row_total, reverse=True):
        total = sum(data[stage][metric] for stage in ACTIVE_STAGES)
        row = [category, key]
        for stage in ACTIVE_STAGES:
            value = data[stage][metric]
            row.extend([value, f"{percent(value, total):.2f}%"])
            totals[stage] += value
        writer.writerow(row)

    grand_total = sum(totals.values())
    row = [category, "TOTAL"]
    for stage in ACTIVE_STAGES:
        row.extend([totals[stage], f"{percent(totals[stage], grand_total):.2f}%"])
    writer.writerow(row)


def summary_pair(values):
    if not values:
        return [0, 0]
    return [round(statistics.mean(values), 2), round(statistics.median(values), 2)]


def summarize_op_latency(op_latency):
    summary = {}
    for op, stage_values in op_latency.items():
        summary[op] = {}
        for stage in ACTIVE_STAGES + ["TOTAL"]:
            values = stage_values[stage]
            avg, median = summary_pair(values)
            summary[op][stage] = {"count": len(values), "avg": avg, "median": median}
    return summary


def latency_avg_median(stage_value):
    if isinstance(stage_value, dict):
        return stage_value.get("avg", 0), stage_value.get("median", 0)
    return summary_pair(stage_value)


def latency_count(stage_value):
    if isinstance(stage_value, dict):
        return stage_value.get("count", 0)
    return len(stage_value)


def combine_latency_summaries(results):
    combined = defaultdict(lambda: {stage: {"count": 0, "avg_total": 0.0, "medians": []} for stage in ACTIVE_STAGES + ["TOTAL"]})
    for result in results:
        for op, stage_values in result["op_latency"].items():
            for stage in ACTIVE_STAGES + ["TOTAL"]:
                count = latency_count(stage_values[stage])
                avg, median = latency_avg_median(stage_values[stage])
                combined[op][stage]["count"] += count
                combined[op][stage]["avg_total"] += avg * count
                if count:
                    combined[op][stage]["medians"].append(median)
    summary = {}
    for op, stage_values in combined.items():
        summary[op] = {}
        for stage, data in stage_values.items():
            count = data["count"]
            avg = round(data["avg_total"] / count, 2) if count else 0
            median = round(statistics.median(data["medians"]), 2) if data["medians"] else 0
            summary[op][stage] = {"count": count, "avg": avg, "median": median}
    return summary


def load_pyplot():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def short_case_label(name):
    return str(name).split("-", 1)[0]


def add_vertical_value_labels(ax, bars, fmt="{:.1f}"):
    for bar in bars:
        height = bar.get_height()
        if height == 0:
            continue
        ax.annotate(fmt.format(height),
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha="center", va="bottom", fontsize=8)


def add_horizontal_value_labels(ax, bars, fmt="{:.1f}"):
    for bar in bars:
        width = bar.get_width()
        if width == 0:
            continue
        ax.annotate(fmt.format(width),
                    xy=(width, bar.get_y() + bar.get_height() / 2),
                    xytext=(3, 0),
                    textcoords="offset points",
                    ha="left", va="center", fontsize=8)


def plot_stacked_ratio(agg, metric, title, output_path, key_label):
    plt = load_pyplot()
    items = sorted(agg.items(), key=lambda item: sum(item[1][stage][metric] for stage in ACTIVE_STAGES), reverse=True)
    if key_label == "op":
        plot_op_stage_ratio_items(plt, items, metric, title, output_path)
        return
    labels = [str(key) for key, _ in items]
    rows = []
    for _, data in items:
        total = sum(data[stage][metric] for stage in ACTIVE_STAGES)
        rows.append([percent(data[stage][metric], total) for stage in ACTIVE_STAGES])

    width = max(10, min(36, len(labels) * 0.45 + 4))
    fig, ax = plt.subplots(figsize=(width, 6))
    bottoms = [0.0] * len(labels)
    for idx, stage in enumerate(ACTIVE_STAGES):
        vals = [row[idx] for row in rows]
        ax.bar(labels, vals, bottom=bottoms, label=stage)
        bottoms = [bottoms[i] + vals[i] for i in range(len(vals))]
    ax.set_title(title)
    ax.set_xlabel(key_label)
    ax.set_ylabel("ratio (%)")
    ax.set_ylim(0, 100)
    ax.legend(loc="upper right")
    ax.tick_params(axis="x", rotation=90)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def plot_op_stage_ratio_items(plt, items, metric, title, output_path):
    if not items:
        return
    fig_height = max(5, len(items) * 3.2)
    fig, axes = plt.subplots(len(items), 1, figsize=(12, fig_height), squeeze=False, constrained_layout=True)
    for ax, (op, data) in zip(axes[:, 0], items):
        total = sum(data[stage][metric] for stage in ACTIVE_STAGES)
        values = [percent(data[stage][metric], total) for stage in ACTIVE_STAGES]
        bars = ax.bar(ACTIVE_STAGES, values)
        add_vertical_value_labels(ax, bars)
        ax.set_title(str(op))
        ax.set_ylabel("ratio (%)")
        ax.set_ylim(0, 100)
        ax.tick_params(axis="x", rotation=20)
    fig.suptitle(f"{title}: one subplot per op")
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def plot_op_latency(op_latency, output_path):
    plt = load_pyplot()
    ops = sorted(op_latency.keys())
    if not ops:
        return
    fig_height = max(5, len(ops) * 3.2)
    fig, axes = plt.subplots(len(ops), 1, figsize=(12, fig_height), squeeze=False, constrained_layout=True)
    for ax, op in zip(axes[:, 0], ops):
        labels = ACTIVE_STAGES + ["TOTAL"]
        avg_values = []
        median_values = []
        for stage in labels:
            avg, median = latency_avg_median(op_latency[op][stage])
            avg_values.append(avg)
            median_values.append(median)
        x = list(range(len(labels)))
        avg_bars = ax.bar([i - 0.2 for i in x], avg_values, width=0.4, label="avg")
        median_bars = ax.bar([i + 0.2 for i in x], median_values, width=0.4, label="median")
        add_vertical_value_labels(ax, avg_bars)
        add_vertical_value_labels(ax, median_bars)
        ax.set_title(str(op))
        ax.set_ylabel("remain cycles")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=20, ha="right")
        ax.legend(loc="upper right")
    fig.suptitle("op stage latency: one subplot per op")
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def analyze_case(case_dir, make_graphs=True):
    log_path = case_dir / "inst_stage.log"
    warp_agg, op_agg, latency = aggregate_inst_stage_log(log_path)

    write_case_csv(case_dir, warp_agg, op_agg, latency)
    if make_graphs:
        graph_dir = case_dir / "inst_stage_graph"
        graph_dir.mkdir(exist_ok=True)
        plot_stacked_ratio(warp_agg, "stall", "warp stage stall ratio", graph_dir / "warp_stage_stall_ratio.png", "warp")
        plot_stacked_ratio(warp_agg, "remain", "warp stage remain ratio", graph_dir / "warp_stage_remain_ratio.png", "warp")
        plot_stacked_ratio(op_agg, "stall", "op stage stall ratio", graph_dir / "op_stage_stall_ratio.png", "op")
        plot_stacked_ratio(op_agg, "remain", "op stage remain ratio", graph_dir / "op_stage_remain_ratio.png", "op")
        plot_op_latency(latency, graph_dir / "op_stage_latency_avg_median.png")

    return {
        "case_dir": case_dir,
        "case_name": case_dir.name,
        "display_name": short_case_label(case_dir.name),
        "warp_agg": warp_agg,
        "op_agg": op_agg,
        "op_latency": summarize_op_latency(latency),
    }


def write_confluence(group_dir, case_results, make_graphs=True):
    confluence_dir = group_dir / "confluence"
    confluence_dir.mkdir(exist_ok=True)
    combined = combine_case_results(group_dir.name, case_results)
    if make_graphs:
        case_stage = build_case_stage_summary(case_results)
        plot_case_stage_ratio(case_stage, "stall", confluence_dir / "case_stage_stall_ratio.png")
        plot_case_stage_ratio(case_stage, "remain", confluence_dir / "case_stage_remain_ratio.png")
        plot_case_op_latency(case_results, "avg", confluence_dir / "case_op_avg_remain_cycles.png")
        plot_case_op_latency(case_results, "median", confluence_dir / "case_op_median_remain_cycles.png")
        plot_stacked_ratio(combined["op_agg"], "stall", "op stage stall ratio", confluence_dir / "op_stage_stall_ratio.png", "op")
        plot_stacked_ratio(combined["op_agg"], "remain", "op stage remain ratio", confluence_dir / "op_stage_remain_ratio.png", "op")
    write_case_op_stage_csv(case_results, confluence_dir / "case_op_stage_stall_remain.csv")
    write_case_op_latency_csv(case_results, confluence_dir / "case_op_remain_cycles.csv")


def build_case_stage_summary(case_results):
    summary = {}
    for result in case_results:
        data = {stage: {"stall": 0, "remain": 0} for stage in ACTIVE_STAGES}
        for warp_data in result["warp_agg"].values():
            for stage in ACTIVE_STAGES:
                data[stage]["stall"] += warp_data[stage]["stall"]
                data[stage]["remain"] += warp_data[stage]["remain"]
        summary[result.get("display_name", result["case_name"])] = data
    return summary


def plot_case_stage_ratio(case_stage, metric, output_path):
    plt = load_pyplot()
    labels = list(case_stage.keys())
    ratio_rows = []
    value_rows = []
    totals = []
    for case in labels:
        total = sum(case_stage[case][stage][metric] for stage in ACTIVE_STAGES)
        totals.append(total)
        value_rows.append([case_stage[case][stage][metric] for stage in ACTIVE_STAGES])
        ratio_rows.append([percent(case_stage[case][stage][metric], total) for stage in ACTIVE_STAGES])

    height = max(6, len(labels) * 0.45 + 3)
    fig, ax = plt.subplots(figsize=(16, height), constrained_layout=True)
    y_pos = list(range(len(labels)))
    lefts = [0.0] * len(labels)
    for idx, stage in enumerate(ACTIVE_STAGES):
        vals = [row[idx] for row in ratio_rows]
        actual_values = [row[idx] for row in value_rows]
        bars = ax.barh(y_pos, vals, left=lefts, label=stage)
        for bar, val, actual in zip(bars, vals, actual_values):
            if val:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_y() + bar.get_height() / 2,
                        f"{val:.1f}%\n{actual:,.0f}", ha="center", va="center", fontsize=7)
        lefts = [lefts[i] + vals[i] for i in range(len(vals))]
    for y, total in zip(y_pos, totals):
        ax.text(101, y, f"total={total:,.0f}", ha="left", va="center", fontsize=8)
    ax.set_title(f"case stage {metric} ratio")
    ax.set_xlabel("ratio (%)")
    ax.set_xlim(0, 116)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels)
    ax.legend(loc="upper right")
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def plot_case_op_latency(case_results, metric, output_path):
    plt = load_pyplot()
    ops = sorted({op for result in case_results for op in result["op_latency"]})
    if not ops:
        return
    fig_height = max(5, len(ops) * 3.4)
    fig, axes = plt.subplots(len(ops), 1, figsize=(16, fig_height), squeeze=False, constrained_layout=True)
    for ax, op in zip(axes[:, 0], ops):
        labels = []
        values = []
        for result in case_results:
            if op not in result["op_latency"]:
                continue
            avg, median = latency_avg_median(result["op_latency"][op]["TOTAL"])
            labels.append(result.get("display_name", result["case_name"]))
            values.append(avg if metric == "avg" else median)
        y_pos = list(range(len(labels)))
        bars = ax.barh(y_pos, values)
        add_horizontal_value_labels(ax, bars)
        ax.set_title(str(op))
        ax.set_xlabel("remain cycles")
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels)
    fig.suptitle(f"case op {metric} remain cycles: one subplot per op")
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def write_case_op_stage_csv(case_results, output_path):
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["case", "op", "stage", "stall", "stall_%", "remain", "remain_%"])
        for result in case_results:
            for op, data in sorted(result["op_agg"].items()):
                stall_total = sum(data[stage]["stall"] for stage in ACTIVE_STAGES)
                remain_total = sum(data[stage]["remain"] for stage in ACTIVE_STAGES)
                for stage in ACTIVE_STAGES:
                    stall = data[stage]["stall"]
                    remain = data[stage]["remain"]
                    writer.writerow([
                        result["case_name"],
                        op,
                        stage,
                        stall,
                        f"{percent(stall, stall_total):.2f}%",
                        remain,
                        f"{percent(remain, remain_total):.2f}%",
                    ])


def write_case_op_latency_csv(case_results, output_path):
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["case", "op", "count", "stage", "avg_remain_cycles", "median_remain_cycles"])
        for result in case_results:
            for op, stage_values in sorted(result["op_latency"].items()):
                count = latency_count(stage_values["TOTAL"])
                for stage in ACTIVE_STAGES + ["TOTAL"]:
                    avg, median = latency_avg_median(stage_values[stage])
                    writer.writerow([result["case_name"], op, count, stage, avg, median])


def combine_case_results(config_name, case_results):
    warp_agg = defaultdict(lambda: {stage: {"stall": 0, "remain": 0} for stage in ACTIVE_STAGES})
    op_agg = defaultdict(lambda: {stage: {"stall": 0, "remain": 0} for stage in ACTIVE_STAGES})
    for result in case_results:
        for warp, data in result["warp_agg"].items():
            for stage in ACTIVE_STAGES:
                warp_agg[warp][stage]["stall"] += data[stage]["stall"]
                warp_agg[warp][stage]["remain"] += data[stage]["remain"]
        for op, data in result["op_agg"].items():
            for stage in ACTIVE_STAGES:
                op_agg[op][stage]["stall"] += data[stage]["stall"]
                op_agg[op][stage]["remain"] += data[stage]["remain"]
    op_latency_values = combine_latency_summaries(case_results)
    return {
        "case_name": config_name,
        "warp_agg": warp_agg,
        "op_agg": op_agg,
        "op_latency": op_latency_values,
    }


def load_config_result_from_confluence(config_dir):
    stage_csv = config_dir / "confluence" / "case_op_stage_stall_remain.csv"
    latency_csv = config_dir / "confluence" / "case_op_remain_cycles.csv"
    if not stage_csv.is_file() or not latency_csv.is_file():
        return None
    op_agg = defaultdict(lambda: {stage: {"stall": 0, "remain": 0} for stage in ACTIVE_STAGES})
    with open(stage_csv, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stage = row["stage"]
            if stage not in ACTIVE_STAGES:
                continue
            op_agg[row["op"]][stage]["stall"] += int(row["stall"])
            op_agg[row["op"]][stage]["remain"] += int(row["remain"])
    op_latency = defaultdict(dict)
    with open(latency_csv, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stage = row["stage"]
            op_latency[row["op"]][stage] = {
                "count": int(row["count"]),
                "avg": float(row["avg_remain_cycles"]),
                "median": float(row["median_remain_cycles"]),
            }
    warp_agg = {"ALL_CASES": {stage: {"stall": 0, "remain": 0} for stage in ACTIVE_STAGES}}
    for op_data in op_agg.values():
        for stage in ACTIVE_STAGES:
            warp_agg["ALL_CASES"][stage]["stall"] += op_data[stage]["stall"]
            warp_agg["ALL_CASES"][stage]["remain"] += op_data[stage]["remain"]
    return {
        "case_name": config_dir.name,
        "warp_agg": warp_agg,
        "op_agg": op_agg,
        "op_latency": op_latency,
    }


def write_root_confluence(root, config_results, make_graphs=True):
    confluence_dir = root / "confluence"
    confluence_dir.mkdir(exist_ok=True)
    combined = combine_case_results(root.name, config_results)
    if make_graphs:
        config_stage = build_case_stage_summary(config_results)
        plot_case_stage_ratio(config_stage, "stall", confluence_dir / "config_stage_stall_ratio.png")
        plot_case_stage_ratio(config_stage, "remain", confluence_dir / "config_stage_remain_ratio.png")
        plot_case_op_latency(config_results, "avg", confluence_dir / "config_op_avg_remain_cycles.png")
        plot_case_op_latency(config_results, "median", confluence_dir / "config_op_median_remain_cycles.png")
        plot_stacked_ratio(combined["op_agg"], "stall", "op_stage_stall_ratio", confluence_dir / "op_stage_stall_ratio.png", "op")
        plot_stacked_ratio(combined["op_agg"], "remain", "op_stage_remain_ratio", confluence_dir / "op_stage_remain_ratio.png", "op")
    write_case_op_stage_csv(config_results, confluence_dir / "config_op_stage_stall_remain.csv")
    write_case_op_latency_csv(config_results, confluence_dir / "config_op_remain_cycles.csv")


def find_case_dirs(root):
    return sorted(path.parent for path in root.rglob("inst_stage.log") if path.is_file())


def group_cases(case_dirs):
    groups = defaultdict(list)
    for case_dir in case_dirs:
        groups[case_dir.parent].append(case_dir)
    return groups


def should_bypass_config(config_dir, config_index, bypass_names, bypass_count):
    if config_index < bypass_count:
        return True
    config_name = config_dir.name
    return any(name and (name == config_name or name in config_name) for name in bypass_names)


def resolve_result_dir(value):
    path = Path(value)
    if path.exists():
        return path.resolve()
    host_prefix = "/Users/bytedance/Desktop/Accel-sim/accel-sim-framework"
    if str(value).startswith(host_prefix):
        docker_path = Path("/accel-sim/accel-sim-framework" + str(value)[len(host_prefix):])
        if docker_path.exists():
            return docker_path.resolve()
    script_dir = Path(__file__).resolve().parent
    regress_result_path = script_dir.parent / "regress_result" / value
    if regress_result_path.exists():
        return regress_result_path.resolve()
    return path.resolve()


def main(result_dir, no_graphs=False, no_case_graphs=False):
    make_graphs = not no_graphs
    case_graphs = make_graphs and not no_case_graphs
    if make_graphs:
        try:
            load_pyplot()
        except ImportError as exc:
            print(f"matplotlib is unavailable ({exc}); writing CSV files only")
            make_graphs = False

    root = resolve_result_dir(result_dir)
    if not root.exists():
        raise SystemExit(f"Result directory does not exist: {root}")

    case_dirs = find_case_dirs(root)
    if not case_dirs:
        raise SystemExit(f"No inst_stage.log found under: {root}")

    print(f"Scanning: {root}")
    print(f"Found {len(case_dirs)} case(s)")
    bypass_names = set(bypass_config_name_list)
    bypass_count = max(0, int(bypass_first_config_count))
    if bypass_names or bypass_count:
        print(f"Config bypass enabled: {len(bypass_names)} name filter(s), first {bypass_count} config(s)")
    config_results = []
    grouped_cases = sorted(group_cases(case_dirs).items())
    for config_index, (group_dir, dirs) in enumerate(grouped_cases):
        print(f"Group [{config_index}]: {group_dir}")
        if should_bypass_config(group_dir, config_index, bypass_names, bypass_count):
            loaded = load_config_result_from_confluence(group_dir)
            if loaded is not None:
                config_results.append(loaded)
                print(f"  bypass config; reused existing confluence summary")
            else:
                print(f"  bypass config requested, but existing confluence CSV is missing; skip this config")
            continue
        case_results = []
        for case_index, case_dir in enumerate(dirs):
            print(f"  analyzing [{case_index}] {case_dir.name}")
            case_results.append(analyze_case(case_dir, make_graphs and case_graphs))
        if not case_results:
            print(f"  no analyzed cases for this group; skip confluence")
            continue
        write_confluence(group_dir, case_results, make_graphs)
        config_results.append(combine_case_results(group_dir.name, case_results))
        print(f"  confluence saved: {group_dir / 'confluence'}")
    if config_results:
        write_root_confluence(root, config_results, make_graphs)
        print(f"Root confluence saved: {root / 'confluence'}")
    else:
        print("No cases analyzed; skip root confluence")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze inst_stage.log files under a completed regression result directory.")
    parser.add_argument("result_dir", nargs="?",
                        help="Completed result directory to scan. Overrides result_path when provided.")
    parser.add_argument("--no-graphs", action="store_true",
                        help="Only write CSV files; skip PNG generation.")
    parser.add_argument("--no-case-graphs", action="store_true",
                        help="Skip per-case PNG generation; confluence PNGs are still generated unless --no-graphs is set.")
    args = parser.parse_args()
    selected_result_path = args.result_dir or result_path
    if not selected_result_path:
        parser.error("set result_path in this script or pass result_dir on the command line")
    main(selected_result_path, args.no_graphs, args.no_case_graphs)

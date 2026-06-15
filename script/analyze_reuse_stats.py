#!/usr/bin/env python3

import argparse
import csv
import math
import re
from collections import defaultdict
from pathlib import Path

from analyze_case_cycles import load_pyplot, resolve_result_dir, short_case_label

result_path = "/Users/bytedance/Desktop/Accel-sim/accel-sim-framework/regress_result/20260615_074224"

REUSE_FIELDS = [
    "reuse_time",
    "rfc_compiler_reuse_time",
    "rfc_compiler_reuse_hit_time",
    "reuse_time_rate",
    "rfc_compiler_reuse_rate",
]


def parse_config(config):
    sched_match = re.search(r"regress_sched_([^_]+)", config)
    values = {"sched": sched_match.group(1) if sched_match else "unknown"}
    for key in ("rfc", "bank", "wbd", "reuse", "ocs", "regb", "ocu", "dp"):
        match = re.search(rf"_{key}(\d+)", config)
        values[key] = int(match.group(1)) if match else None
    return values


def parse_last_reuse_stats(log_path):
    patterns = {
        field: re.compile(rf"^\s*{field}\s*=\s*([0-9]+(?:\.[0-9]+)?)")
        for field in REUSE_FIELDS
    }
    values = {field: None for field in REUSE_FIELDS}
    with open(log_path, "r", errors="ignore") as f:
        for line in f:
            for field, pattern in patterns.items():
                match = pattern.search(line)
                if match:
                    raw_value = match.group(1)
                    if field.endswith("_rate"):
                        values[field] = float(raw_value)
                    else:
                        values[field] = int(float(raw_value))
    return values


def find_reuse_records(root):
    records = []
    for log_path in sorted(root.rglob("*.log")):
        if log_path.name == "inst_stage.log":
            continue
        case_dir = log_path.parent
        config_dir = case_dir.parent
        if config_dir == root or config_dir.name == "confluence":
            continue
        stats = parse_last_reuse_stats(log_path)
        if any(stats[field] is None for field in REUSE_FIELDS):
            continue
        config_values = parse_config(config_dir.name)
        compiler_total = stats["rfc_compiler_reuse_time"]
        compiler_hit = stats["rfc_compiler_reuse_hit_time"]
        all_reuse = stats["reuse_time"]
        records.append({
            "config": config_dir.name,
            "case": case_dir.name,
            "case_label": short_case_label(case_dir.name),
            "log_path": log_path,
            **config_values,
            **stats,
            "computed_reuse_time_rate": all_reuse / compiler_total if compiler_total else math.nan,
            "computed_rfc_compiler_reuse_rate": compiler_hit / compiler_total if compiler_total else math.nan,
            "compiler_reuse_coverage_pct": compiler_total / all_reuse * 100 if all_reuse else math.nan,
            "compiler_reuse_hit_over_all_reuse_pct": compiler_hit / all_reuse * 100 if all_reuse else math.nan,
        })
    return records


def write_rows_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_root_csv(root, records):
    confluence_dir = root / "confluence"
    fields = [
        "case", "case_label", "config", "sched", "ocs", "reuse", "rfc", "bank", "wbd", "regb", "ocu", "dp",
        "reuse_time", "rfc_compiler_reuse_time", "rfc_compiler_reuse_hit_time",
        "reuse_time_rate", "rfc_compiler_reuse_rate",
        "computed_reuse_time_rate", "computed_rfc_compiler_reuse_rate",
        "compiler_reuse_coverage_pct", "compiler_reuse_hit_over_all_reuse_pct", "log_path",
    ]
    csv_path = confluence_dir / "reuse_stats_by_case_config.csv"
    write_rows_csv(csv_path, sorted(records, key=lambda r: (r["case_label"], r["sched"], r["ocs"], r["config"])), fields)
    return csv_path


def write_summary_csvs(root, records):
    confluence_dir = root / "confluence"
    confluence_dir.mkdir(exist_ok=True)

    by_sched_ocs = defaultdict(list)
    by_case_sched_ocs = defaultdict(list)
    for record in records:
        by_sched_ocs[(record["sched"], record["ocs"])].append(record)
        by_case_sched_ocs[(record["case_label"], record["sched"], record["ocs"])].append(record)

    summary_rows = []
    for (sched, ocs), group in sorted(by_sched_ocs.items()):
        reuse_time = sum(row["reuse_time"] for row in group)
        compiler_time = sum(row["rfc_compiler_reuse_time"] for row in group)
        compiler_hit = sum(row["rfc_compiler_reuse_hit_time"] for row in group)
        summary_rows.append({
            "sched": sched,
            "ocs": ocs,
            "case_count": len(group),
            "reuse_time": reuse_time,
            "rfc_compiler_reuse_time": compiler_time,
            "rfc_compiler_reuse_hit_time": compiler_hit,
            "reuse_time_rate": reuse_time / compiler_time if compiler_time else math.nan,
            "rfc_compiler_reuse_rate": compiler_hit / compiler_time if compiler_time else math.nan,
            "compiler_reuse_coverage_pct": compiler_time / reuse_time * 100 if reuse_time else math.nan,
            "compiler_reuse_hit_over_all_reuse_pct": compiler_hit / reuse_time * 100 if reuse_time else math.nan,
        })
    summary_fields = [
        "sched", "ocs", "case_count", "reuse_time", "rfc_compiler_reuse_time", "rfc_compiler_reuse_hit_time",
        "reuse_time_rate", "rfc_compiler_reuse_rate", "compiler_reuse_coverage_pct", "compiler_reuse_hit_over_all_reuse_pct",
    ]
    write_rows_csv(confluence_dir / "reuse_summary_by_sched_ocs.csv", summary_rows, summary_fields)

    case_rows = []
    for (case_label, sched, ocs), group in sorted(by_case_sched_ocs.items()):
        reuse_time = sum(row["reuse_time"] for row in group)
        compiler_time = sum(row["rfc_compiler_reuse_time"] for row in group)
        compiler_hit = sum(row["rfc_compiler_reuse_hit_time"] for row in group)
        case_rows.append({
            "case_label": case_label,
            "sched": sched,
            "ocs": ocs,
            "reuse_time": reuse_time,
            "rfc_compiler_reuse_time": compiler_time,
            "rfc_compiler_reuse_hit_time": compiler_hit,
            "reuse_time_rate": reuse_time / compiler_time if compiler_time else math.nan,
            "rfc_compiler_reuse_rate": compiler_hit / compiler_time if compiler_time else math.nan,
            "compiler_reuse_coverage_pct": compiler_time / reuse_time * 100 if reuse_time else math.nan,
            "compiler_reuse_hit_over_all_reuse_pct": compiler_hit / reuse_time * 100 if reuse_time else math.nan,
        })
    case_fields = [
        "case_label", "sched", "ocs", "reuse_time", "rfc_compiler_reuse_time", "rfc_compiler_reuse_hit_time",
        "reuse_time_rate", "rfc_compiler_reuse_rate", "compiler_reuse_coverage_pct", "compiler_reuse_hit_over_all_reuse_pct",
    ]
    write_rows_csv(confluence_dir / "reuse_summary_by_case_sched_ocs.csv", case_rows, case_fields)
    return summary_rows, case_rows


def plot_metric_by_sched_ocs(root, summary_rows, metric, ylabel, title, output_name):
    plt = load_pyplot()
    sched_to_rows = defaultdict(list)
    for row in summary_rows:
        sched_to_rows[row["sched"]].append(row)

    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    for sched, rows in sorted(sched_to_rows.items()):
        rows = sorted(rows, key=lambda row: row["ocs"])
        ax.plot([row["ocs"] for row in rows], [row[metric] for row in rows], marker="o", label=sched.upper())
    ax.set_xlabel("OC/RFC entries per scheduler (ocs)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    output_path = root / "confluence" / output_name
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return output_path


def build_case_metric_lookup(case_rows, metric):
    by_ocs = defaultdict(dict)
    for row in case_rows:
        by_ocs[row["ocs"]].setdefault(row["case_label"], {})[row["sched"]] = row[metric]
    return by_ocs


def plot_case_metric_delta(root, case_rows, metric, output_name):
    plt = load_pyplot()
    by_ocs = build_case_metric_lookup(case_rows, metric)

    cases = sorted({row["case_label"] for row in case_rows})
    ocs_values = sorted(by_ocs.keys())
    x_positions = list(range(len(cases)))
    width = 0.8 / max(1, len(ocs_values))

    fig, ax = plt.subplots(figsize=(13, 5.6))
    for idx, ocs in enumerate(ocs_values):
        deltas = []
        for case in cases:
            values = by_ocs[ocs].get(case, {})
            gto = values.get("gto")
            lrr = values.get("lrr")
            deltas.append(lrr - gto if gto is not None and lrr is not None else 0)
        xs = [x + (idx - (len(ocs_values) - 1) / 2) * width for x in x_positions]
        ax.bar(xs, deltas, width=width, label=f"ocs={ocs}")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x_positions)
    ax.set_xticklabels(cases, rotation=45, ha="right")
    ax.set_ylabel(f"LRR - GTO {metric}")
    ax.set_title(f"Per-case LRR vs GTO delta: positive means LRR is larger")
    ax.grid(axis="y", alpha=0.3)
    ax.legend(ncol=min(4, len(ocs_values)))
    fig.tight_layout()
    output_path = root / "confluence" / output_name
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return output_path


def plot_case_metric_grouped_bars(root, case_rows, metric, ylabel, output_prefix):
    plt = load_pyplot()
    by_ocs = build_case_metric_lookup(case_rows, metric)
    cases = sorted({row["case_label"] for row in case_rows})
    outputs = []

    for ocs in sorted(by_ocs.keys()):
        gto_values = [by_ocs[ocs].get(case, {}).get("gto") for case in cases]
        lrr_values = [by_ocs[ocs].get(case, {}).get("lrr") for case in cases]
        x_positions = list(range(len(cases)))
        width = 0.38

        fig, ax = plt.subplots(figsize=(13, 5.6))
        ax.bar([x - width / 2 for x in x_positions], gto_values, width=width, label="GTO", color="#4C78A8")
        ax.bar([x + width / 2 for x in x_positions], lrr_values, width=width, label="LRR", color="#F58518")
        for idx, (gto, lrr) in enumerate(zip(gto_values, lrr_values)):
            if gto is None or lrr is None:
                continue
            winner = "LRR" if lrr > gto else "GTO" if gto > lrr else "="
            y = max(gto, lrr)
            ax.text(idx, y, winner, ha="center", va="bottom", fontsize=8)
        ax.set_xticks(x_positions)
        ax.set_xticklabels(cases, rotation=45, ha="right")
        ax.set_ylabel(ylabel)
        ax.set_title(f"GTO vs LRR {metric}, ocs={ocs}; label marks the larger value")
        ax.grid(axis="y", alpha=0.3)
        ax.legend()
        fig.tight_layout()
        output_path = root / "confluence" / f"{output_prefix}_ocs{ocs}.png"
        fig.savefig(output_path, dpi=160)
        plt.close(fig)
        outputs.append(output_path)
    return outputs


def plot_case_metric_grouped_bars_combined(root, case_rows, metric, ylabel, output_name):
    plt = load_pyplot()
    by_ocs = build_case_metric_lookup(case_rows, metric)
    cases = sorted({row["case_label"] for row in case_rows})
    ocs_values = sorted(by_ocs.keys())
    cols = 2
    rows = math.ceil(len(ocs_values) / cols)

    fig, axes = plt.subplots(rows, cols, figsize=(18, 4.8 * rows), squeeze=False, sharey=True)
    x_positions = list(range(len(cases)))
    width = 0.38

    for idx, ocs in enumerate(ocs_values):
        ax = axes[idx // cols][idx % cols]
        gto_values = [by_ocs[ocs].get(case, {}).get("gto") for case in cases]
        lrr_values = [by_ocs[ocs].get(case, {}).get("lrr") for case in cases]
        ax.bar([x - width / 2 for x in x_positions], gto_values, width=width, label="GTO", color="#4C78A8")
        ax.bar([x + width / 2 for x in x_positions], lrr_values, width=width, label="LRR", color="#F58518")
        for case_idx, (gto, lrr) in enumerate(zip(gto_values, lrr_values)):
            if gto is None or lrr is None:
                continue
            winner = "LRR" if lrr > gto else "GTO" if gto > lrr else "="
            ax.text(case_idx, max(gto, lrr), winner, ha="center", va="bottom", fontsize=7)
        ax.set_title(f"ocs={ocs}")
        ax.set_xticks(x_positions)
        ax.set_xticklabels(cases, rotation=45, ha="right", fontsize=8)
        ax.grid(axis="y", alpha=0.3)
        if idx % cols == 0:
            ax.set_ylabel(ylabel)
        if idx == 0:
            ax.legend()

    for empty_idx in range(len(ocs_values), rows * cols):
        axes[empty_idx // cols][empty_idx % cols].axis("off")

    fig.suptitle(f"GTO vs LRR {metric} by case and ocs; label marks the larger value", y=0.995)
    fig.tight_layout()
    output_path = root / "confluence" / output_name
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return output_path


def plot_case_metric_winner_heatmap(root, case_rows, metric, output_name):
    plt = load_pyplot()
    by_ocs = build_case_metric_lookup(case_rows, metric)
    cases = sorted({row["case_label"] for row in case_rows})
    ocs_values = sorted(by_ocs.keys())
    matrix = []
    labels = []
    for case in cases:
        row_values = []
        row_labels = []
        for ocs in ocs_values:
            values = by_ocs[ocs].get(case, {})
            gto = values.get("gto")
            lrr = values.get("lrr")
            if gto is None or lrr is None:
                row_values.append(0)
                row_labels.append("NA")
            else:
                delta = lrr - gto
                row_values.append(delta)
                if abs(delta) < 1e-12:
                    row_labels.append("=")
                else:
                    row_labels.append("LRR" if delta > 0 else "GTO")
        matrix.append(row_values)
        labels.append(row_labels)

    max_abs = max([abs(value) for row in matrix for value in row] + [1e-12])
    fig, ax = plt.subplots(figsize=(8.5, 6.2))
    image = ax.imshow(matrix, cmap="coolwarm", vmin=-max_abs, vmax=max_abs, aspect="auto")
    ax.set_xticks(range(len(ocs_values)))
    ax.set_xticklabels([f"ocs={ocs}" for ocs in ocs_values])
    ax.set_yticks(range(len(cases)))
    ax.set_yticklabels(cases)
    for y, row_labels in enumerate(labels):
        for x, label in enumerate(row_labels):
            ax.text(x, y, label, ha="center", va="center", fontsize=8, color="black")
    ax.set_title(f"Winner heatmap for {metric}; red=LRR larger, blue=GTO larger")
    fig.colorbar(image, ax=ax, label=f"LRR - GTO {metric}")
    fig.tight_layout()
    output_path = root / "confluence" / output_name
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return output_path


def plot_case_count_and_rate_by_config(root, case_rows, count_metric, rate_metric, count_ylabel, count_label, rate_label, title, output_name):
    plt = load_pyplot()
    cases = sorted({row["case_label"] for row in case_rows})
    ocs_values = sorted({row["ocs"] for row in case_rows})
    scheds = ["gto", "lrr"]
    lookup = {(row["case_label"], row["ocs"], row["sched"]): row for row in case_rows}

    cols = 2
    rows = math.ceil(len(cases) / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(16, 4.3 * rows), squeeze=False)
    width = 0.36
    x_positions = list(range(len(ocs_values)))
    colors = {"gto": "#4C78A8", "lrr": "#F58518"}

    for case_idx, case in enumerate(cases):
        ax = axes[case_idx // cols][case_idx % cols]
        max_count = 0
        for sched_idx, sched in enumerate(scheds):
            counts = []
            rates = []
            for ocs in ocs_values:
                row = lookup.get((case, ocs, sched))
                counts.append(row[count_metric] if row else 0)
                rates.append(row[rate_metric] if row else math.nan)
            xs = [x + (sched_idx - 0.5) * width for x in x_positions]
            bars = ax.bar(xs, counts, width=width, label=sched.upper(), color=colors[sched])
            max_count = max(max_count, max(counts) if counts else 0)
            for bar, count, rate in zip(bars, counts, rates):
                if count == 0 or math.isnan(rate):
                    continue
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height(),
                    f"{count_label}={count}\nratio={rate:.3f}",
                    ha="center",
                    va="bottom",
                    fontsize=6,
                )
        ax.set_title(case)
        ax.set_xticks(x_positions)
        ax.set_xticklabels([f"ocs={ocs}" for ocs in ocs_values])
        ax.set_ylabel(count_ylabel)
        ax.grid(axis="y", alpha=0.3)
        if max_count > 0:
            ax.set_ylim(0, max_count * 1.35)
        if case_idx == 0:
            ax.legend(fontsize=8)

    for empty_idx in range(len(cases), rows * cols):
        axes[empty_idx // cols][empty_idx % cols].axis("off")

    fig.suptitle(title, y=0.995)
    fig.tight_layout()
    output_path = root / "confluence" / output_name
    fig.savefig(output_path, dpi=170)
    plt.close(fig)
    return output_path


def plot_all(root, summary_rows, case_rows):
    outputs = []
    outputs.append(plot_metric_by_sched_ocs(
        root,
        summary_rows,
        "reuse_time_rate",
        "reuse_time / compiler_reuse_time",
        "Different configs: reuse_time_rate from log",
        "config_reuse_time_rate.png",
    ))
    outputs.append(plot_metric_by_sched_ocs(
        root,
        summary_rows,
        "rfc_compiler_reuse_rate",
        "compiler reuse hit / compiler reuse candidate",
        "Different configs: compiler_reuse_rate from log",
        "config_compiler_reuse_rate.png",
    ))
    outputs.append(plot_case_count_and_rate_by_config(
        root,
        case_rows,
        "reuse_time",
        "reuse_time_rate",
        "reuse_time count",
        "reuse",
        "reuse_time_rate",
        "Per-case all-reuse count and reuse_time_rate across configs",
        "case_config_reuse_time_count_and_rate.png",
    ))
    outputs.append(plot_case_count_and_rate_by_config(
        root,
        case_rows,
        "rfc_compiler_reuse_hit_time",
        "rfc_compiler_reuse_rate",
        "compiler reuse hit count",
        "hit",
        "compiler_reuse_rate",
        "Per-case compiler reuse hit count and compiler_reuse_rate across configs",
        "case_config_compiler_reuse_count_and_rate.png",
    ))
    return outputs


def main(root, no_graphs=False):
    root = resolve_result_dir(root)
    records = find_reuse_records(root)
    if not records:
        raise SystemExit(f"No reuse records found under {root}")

    root_csv = write_root_csv(root, records)
    summary_rows, case_rows = write_summary_csvs(root, records)

    graph_paths = []
    if not no_graphs:
        graph_paths = plot_all(root, summary_rows, case_rows)

    print(f"Parsed reuse stats from {len(records)} case logs")
    print(f"Wrote {root_csv}")
    print(f"Wrote {root / 'confluence' / 'reuse_summary_by_sched_ocs.csv'}")
    print(f"Wrote {root / 'confluence' / 'reuse_summary_by_case_sched_ocs.csv'}")
    for graph_path in graph_paths:
        print(f"Wrote {graph_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze RFC reuse statistics from Accel-Sim case logs.")
    parser.add_argument("result_dir", nargs="?", default=result_path,
                        help="Result directory path or name under accel-sim-framework/regress_result")
    parser.add_argument("--no-graphs", action="store_true", help="Only write CSV files, skip PNG graphs")
    args = parser.parse_args()
    main(args.result_dir, args.no_graphs)

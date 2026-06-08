#!/usr/bin/env python3
"""
Post-process accel-sim results: copy .e/.o/inst_stage.log from sim_run_12.8/
into a clean regress_result/{launch_name}_{timestamp}/ directory, with renamed files.

Usage:
    python3 organize_results.py \\
        --sim-dir sim_run_12.8 \\
        --config MY_RTX3070-SASS \\
        --launch-name myTest \\
        [--output-dir regress_result]
"""

import os
import glob
import re
import shutil
from datetime import datetime
from argparse import ArgumentParser


def find_case_dirs(sim_dir, config, allowed_cases=None):
    """
    Walk sim_dir to find all case run directories.
    Returns list of (case_name, case_run_dir)
    where case_run_dir is .../MY_RTX3070-SASS/
    """
    results = []
    sim_dir = os.path.abspath(sim_dir)
    for root, dirs, files in os.walk(sim_dir):
        if os.path.basename(root) == config:
            # root = .../sim_run_12.8/benchmark_name/case_args/MY_RTX3070-SASS
            case_run_dir = root
            # Derive case_name from the parent directories
            parts = os.path.relpath(root, sim_dir).split(os.sep)
            # parts = [benchmark_name, case_args, MY_RTX3070-SASS]
            if len(parts) >= 2:
                case_name = os.path.join(parts[0], parts[1]).replace(os.sep, "/")
            else:
                case_name = parts[0]
            if allowed_cases and case_name not in allowed_cases:
                continue
            results.append((case_name, case_run_dir))
    return results


def find_newest_file(case_run_dir, patterns, min_mtime=None, required_text=None):
    matches = []
    for pattern in patterns:
        matches.extend(glob.glob(os.path.join(case_run_dir, pattern)))
    files = [path for path in matches if os.path.isfile(path)]
    if min_mtime is not None:
        files = [path for path in files if os.path.getmtime(path) >= min_mtime]
    if required_text is not None:
        filtered = []
        for path in files:
            with open(path, "r", errors="ignore") as f:
                if required_text in f.read():
                    filtered.append(path)
        files = filtered
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def find_files(case_run_dir, case_name):
    """
    Find result files in the case run directory.
    Returns dict with keys: error, log, stage
    """
    result = {}

    # Find inst_stage.log
    stage_log = os.path.join(case_run_dir, "inst_stage.log")
    if os.path.isfile(stage_log):
        result["stage"] = stage_log

    # Find gpgpusim.config (copy as regress.config)
    config_file = os.path.join(case_run_dir, "gpgpusim.config")
    config_mtime = None
    if os.path.isfile(config_file):
        result["config"] = config_file
        config_mtime = os.path.getmtime(config_file)

    log_file = find_newest_file(case_run_dir, ["gpgpu-sim-out*.txt", "output.log"], config_mtime)
    if log_file is None:
        log_file = find_newest_file(case_run_dir, ["gpgpusim.o*", "*.o*"], config_mtime, "GPGPU-Sim")
    if log_file:
        result["log"] = log_file

    error_file = find_newest_file(case_run_dir, ["gpgpusim.e*"])
    if error_file:
        result["error"] = error_file

    return result


def sanitize_filename(name):
    """Replace path separators and problematic chars in filenames."""
    return name.replace("/", "_").replace("\\", "_").replace(" ", "_")


def organize_results(sim_dir, config, launch_name, output_dir, case_filter=None):
    """Main function: find, copy, and rename result files."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_root = os.path.join(output_dir, f"{launch_name}_{timestamp}")
    os.makedirs(dest_root, exist_ok=True)

    allowed_cases = None
    if case_filter:
        allowed_cases = {case.strip() for case in case_filter.split(",") if case.strip()}

    cases = find_case_dirs(sim_dir, config, allowed_cases)
    print(f"Found {len(cases)} case directories under config '{config}'")

    copied_count = 0
    for case_name, case_run_dir in cases:
        files = find_files(case_run_dir, case_name)
        if not files:
            continue

        # Create case folder
        safe_case = sanitize_filename(case_name)
        case_dest = os.path.join(dest_root, safe_case)
        os.makedirs(case_dest, exist_ok=True)
        copied = False

        # Copy error file → {case_name}.error
        if "error" in files:
            dest = os.path.join(case_dest, f"{safe_case}.error")
            shutil.copy2(files["error"], dest)
            copied = True

        # Copy output file → {case_name}.log
        if "log" in files:
            dest = os.path.join(case_dest, f"{safe_case}.log")
            shutil.copy2(files["log"], dest)
            copied = True

        # Copy inst_stage.log
        if "stage" in files:
            dest = os.path.join(case_dest, "inst_stage.log")
            shutil.copy2(files["stage"], dest)
            copied = True

        # Copy gpgpusim.config → regress.config
        if "config" in files:
            dest = os.path.join(case_dest, "regress.config")
            shutil.copy2(files["config"], dest)
            copied = True

        if copied:
            copied_count += 1
            print(f"  [{safe_case}] → {case_dest}")

    print(f"\nDone: {copied_count} cases organized into {dest_root}")


if __name__ == "__main__":
    parser = ArgumentParser(description="Organize accel-sim result files")
    parser.add_argument("--sim-dir", required=True, help="Path to sim_run_12.8 directory")
    parser.add_argument("--config", default="MY_RTX3070-SASS", help="Config name (default: MY_RTX3070-SASS)")
    parser.add_argument("--launch-name", "-N", default="myTest", help="Launch name for output folder")
    parser.add_argument("--output-dir", default=None, help="Output root directory (default: sibling of sim-dir)")
    parser.add_argument("--case-filter", default=None, help="Comma-separated case names to copy")
    args = parser.parse_args()

    sim_dir = os.path.abspath(args.sim_dir)
    if args.output_dir:
        output_dir = os.path.abspath(args.output_dir)
    else:
        output_dir = os.path.join(os.path.dirname(sim_dir), "regress_result")

    organize_results(sim_dir, args.config, args.launch_name, output_dir, args.case_filter)

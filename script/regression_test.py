#!/usr/bin/env python3
"""
regression_test.py — RFC parameter sweep for accel-sim

For each parameter combo:
1. creates a unique config dir temp_{tag}/ from MY_RTX3070
2. overwrites its gpgpusim.config with test params
3. calls run_simulations.py -C temp_{tag}-SASS (blocks until all jobs + organize complete)
4. result appears in both sim_run_12.8/.../temp_{tag}-SASS/ and regress_result/{name}_*/
"""

import itertools, os, re, shutil, subprocess, sys, time, glob, socket
from datetime import datetime
from argparse import ArgumentParser

# ── paths ──
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
ROOT         = os.path.dirname(SCRIPT_DIR)          # accel-sim-framework/
RUN_SIM      = os.path.join(ROOT, "util", "job_launching", "run_simulations.py")
ORGANIZE     = os.path.join(SCRIPT_DIR, "organize_results.py")

ORIG_CFG_GP = os.path.join(ROOT, "gpu-simulator", "gpgpu-sim",  "configs", "tested-cfgs", "MY_RTX3070")
ORIG_CFG_AS = os.path.join(ROOT, "gpu-simulator", "configs",    "tested-cfgs", "MY_RTX3070")
TEMP_CFG_GP = os.path.join(ROOT, "gpu-simulator", "gpgpu-sim",  "configs", "tested-cfgs", "temp")
TEMP_CFG_AS = os.path.join(ROOT, "gpu-simulator", "configs",    "tested-cfgs", "temp")

# ── parameter defaults & sweep sets ──
# These are the base values for ALL params.
# When rfc=1 we sweep RFC params; when rfc=0 we sweep non-RFC params.
PARAM_DEFAULTS = {
    "-gpgpu_scheduler"  :               "gto",  
    "-gpgpu_is_use_rfc":                 1,
    "-gpgpu_rfc_bank_num":               2,
    "-gpgpu_writeback_stack_deepth":     1,
    "-gpgpu_is_compiler_ctrl_reuse":     1,
    "-gpgpu_rfc_or_oc_per_scheduler_num": 1,
    "-gpgpu_num_reg_banks":              8,
    "-gpgpu_operand_collector_num_units_gen": 8,
    "-gpgpu_num_dp_units":               4,
}

# which params to sweep for each rfc mode
PARAM_SWEEP = {
    # rfc=0 → non-RFC params matter
    # 0: {
    #     "-gpgpu_scheduler":                  ["gto", "lrr"],
    #     "-gpgpu_num_reg_banks":              [8],
    #     "-gpgpu_operand_collector_num_units_gen": [4, 8],
    # },
    # rfc=1 → RFC params matter
    1: {
        "-gpgpu_scheduler":                  ["gto", "lrr"],
        "-gpgpu_rfc_bank_num":               [2],
        "-gpgpu_writeback_stack_deepth":     [1],
        "-gpgpu_is_compiler_ctrl_reuse":     [0],
        "-gpgpu_rfc_or_oc_per_scheduler_num": [1, 2, 4, 6],
        "-gpgpu_num_dp_units":               [4],
    },
}

PARAM_ALIAS = {
    "-gpgpu_is_use_rfc":                 "rfc",
    "-gpgpu_scheduler":                  "sched_",
    "-gpgpu_rfc_bank_num":               "bank",
    "-gpgpu_writeback_stack_deepth":     "wbd",
    "-gpgpu_is_compiler_ctrl_reuse":     "reuse",
    "-gpgpu_rfc_or_oc_per_scheduler_num": "ocs",
    "-gpgpu_num_reg_banks":              "regb",
    "-gpgpu_operand_collector_num_units_gen": "ocu",
    "-gpgpu_num_dp_units":               "dp",
}

# ── helpers ──

def label(params):
    return "_".join(f"{PARAM_ALIAS[k]}{v}" for k, v in params.items() if k in PARAM_ALIAS)


def write_config(template_path, params, out_path):
    managed = set(PARAM_DEFAULTS) | set(k for v in PARAM_SWEEP.values() for k in v)
    with open(template_path) as f:
        lines = [l for l in f if not any(l.strip().startswith(k) for k in managed)]
    lines.append("\n# ── regression params ──\n")
    for k, v in params.items():
        lines.append(f"{k} {v}\n")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.writelines(lines)


def refresh_temp():
    """rm -rf temp/ then cp -r MY_RTX3070/ → temp/ for both config dirs"""
    for src, dst in [(ORIG_CFG_GP, TEMP_CFG_GP), (ORIG_CFG_AS, TEMP_CFG_AS)]:
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)


# ── main ──

def main():
    p = ArgumentParser()
    p.add_argument("--base-config", "-b",
                   default=os.path.join(ROOT, "gpu-simulator", "gpgpu-sim",
                                        "configs", "tested-cfgs", "MY_RTX3070", "gpgpusim.config"))
    p.add_argument("--benchmark", "-B", default="rodinia_2.0-ft")
    p.add_argument("--traces", "-T", default=os.path.join(ROOT, os.pardir, "traces", "device-0", "12.6"))
    p.add_argument("--launch-name", "-N", default="regress")
    p.add_argument("--timeout", type=int, default=24)
    p.add_argument("--cores", type=int, default=8)
    p.add_argument("--rfc", type=int, nargs="+", choices=[0, 1],
                   default=sorted(PARAM_SWEEP.keys()),
                   help="RFC modes to test (default: all modes in PARAM_SWEEP)")
    args = p.parse_args()

    # Determine which rfc modes to run
    rfc_modes = sorted(set(args.rfc))

    # Build combo list: for each requested rfc mode, sweep its own parameters
    combos = []
    for rfc_val in rfc_modes:
        base = dict(PARAM_DEFAULTS)
        base["-gpgpu_is_use_rfc"] = rfc_val
        sweep_keys = list(PARAM_SWEEP[rfc_val].keys())
        sweep_vals = [PARAM_SWEEP[rfc_val][k] for k in sweep_keys]
        for choice in itertools.product(*sweep_vals):
            params = dict(base)
            for k, v in zip(sweep_keys, choice):
                params[k] = v
            combos.append(params)

    total = len(combos)
    results = []
    batch_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_dir = os.path.join(ROOT, "regress_result", batch_time)
    os.makedirs(batch_dir, exist_ok=True)
    print(f"Regression result root: {batch_dir}", flush=True)

    for i, combo in enumerate(combos):
        tag = label(combo)
        name = f"{args.launch_name}_{tag}"

        print(f"[{i+1}/{total}] {tag}", flush=True)
        print(f"  {combo}", flush=True)

        # 1. refresh temp config dir + overwrite gpgpusim.config
        refresh_temp()
        write_config(args.base_config, combo,
                     os.path.join(TEMP_CFG_GP, "gpgpusim.config"))

        # 2. run_simulations is blocking: waits for all jobs + copies to regress_result
        cmd = [sys.executable, RUN_SIM,
               "-B", args.benchmark,
               "-C", "temp-SASS",
               "-T", args.traces,
               "-N", name,
               "--regress-output-dir", batch_dir]
        start_time = time.time()
        completed = subprocess.run(cmd)

        # 3. verify regress_result exists
        regress_dirs = glob.glob(os.path.join(batch_dir, f"{name}_*"))
        regress_dirs = [d for d in regress_dirs if os.path.getmtime(d) >= start_time]
        regress_dirs.sort(key=os.path.getmtime, reverse=True)
        res_dir = regress_dirs[0] if completed.returncode == 0 and regress_dirs else None
        if res_dir:
            case_logs = []
            for case_dir in glob.glob(os.path.join(res_dir, "*")):
                if os.path.isdir(case_dir):
                    case_name = os.path.basename(case_dir)
                    case_logs.extend(glob.glob(os.path.join(case_dir, f"{case_name}.log")))
            if not case_logs:
                res_dir = None
        results.append((tag, combo, res_dir))
        if res_dir:
            print(f"  ✅ → {res_dir}")
        else:
            print(f"  ❌ no regress_result for {name}")
        print()

    # summary
    print("═" * 50)
    print("  SUMMARY")
    print("═" * 50)
    ok = sum(1 for _, _, r in results if r)
    for tag, _, r in results:
        print(f"  {tag:40s} {'✅' if r else '❌'}")
    print("═" * 50)
    print(f"  {ok}/{total} passed")


if __name__ == "__main__":
    main()

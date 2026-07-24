# GPU Operand Collector / RFC Microarchitecture Study (based on Accel-Sim)

This repository is forked from the [Accel-Sim framework](https://github.com/accel-sim/accel-sim-framework) (original README: [README_old.md](README_old.md)). It extends the GPGPU-Sim timing model with an **RFC (Register File Cache)-style refactoring of the Operand Collector and multi-level performance counter instrumentation**, to systematically answer one question:

> **Where is the performance benefit boundary of an RFC-style structure, and where does the bottleneck migrate once it saturates?**

Author: Qiaoliang Ye (yqiaoliang@outlook.com)

---

## Key Findings (10 Rodinia workloads, SASS trace-driven)

1. **Scheduling policy**: GTO outperforms LRR by 0.57%–0.84% in geometric-mean cycles across all RFC/OC capacity configurations (best on 7/10 workloads), and produces stronger short-term operand locality (reuse_time_rate 2.415 vs 1.724 @ ocs=1)
2. **Reuse behavior**: 512K total reuse opportunities observed, while compiler `.reuse` hint candidates cover only 41% of them with a 38.54% candidate hit rate — the compiler hint policy is conservative
3. **Capacity benefit boundary**: RFC/OC entry sweep (ocs=1–8) shows performance saturates around ocs≈3 (geometric-mean cycles drop by only 2.45%), corroborating NVIDIA's engineering choice of ocs=2
4. **Bottleneck attribution**: stall reason counters show the bottleneck migrates from entry allocation (RFC_NUM_CONFLICT 51.3%→6.4%) to downstream execution backpressure (EXEC_NUM_CONFLICT 48.5%→93.4%); LOAD_OP/DP_OP contribute 94% of the total waiting
5. **Controlled-variable validation**: increasing DP units from 4 to 12 reduces DP_OP OC stalls by 79% and total cycles of hotspot/backprop by 28.2%/19.2% respectively, while load-heavy workloads remain completely unchanged — the selective response validates the attribution

Full experiment reports (with all data tables and figures):

- [`result/sweep_rfc_num/sweep_rfc_num_result.md`](result/sweep_rfc_num/sweep_rfc_num_result.md) — RFC capacity sweep, stall reason attribution, DP unit validation
- [`result/scheduler_reuse_policy/scheduler_reuse_policy_result.md`](result/scheduler_reuse_policy/scheduler_reuse_policy_result.md) — GTO/LRR comparison and reuse behavior analysis

## Code Changes

Changes are concentrated in the GPGPU-Sim timing model (`gpu-simulator/gpgpu-sim/src/gpgpu-sim/`):

| Location | Change |
|------|---------|
| `shader.cc` / `shader.h` — `opndcoll_rfu_t` | RFC-style refactoring of the Operand Collector: parameterized entry capacity (ocs), cache-like retention and replacement logic |
| Same as above | Three-way OC stall reason counters: `RFC_NUM_CONFLICT` (entry allocation failure) / `BANK_CONFLICT` (RF bank arbitration failure) / `EXEC_NUM_CONFLICT` (operands ready but downstream dispatch backpressure), bucketed by op type |
| Same as above | Bypass reuse statistics (non-intrusive to timing): `reuse_time` (total reuse opportunities) / `rfc_compiler_reuse_time` (compiler `.reuse` hint candidates) / `rfc_compiler_reuse_hit_time` |
| Same as above — stage statistics | Layered stall/remain statistics across four stages: SCHEDULER / OPERAND_COLLECTOR / EXECUTION_PIPELINE / WRITEBACK |
| `script/` | Batch experiment running, log parsing, derived-CSV generation and plotting scripts (pandas/matplotlib) |

## Reproduction

```bash
# 1. Build following the upstream Accel-Sim flow (see README_old.md), SASS trace mode
# 2. Key sweep parameters (example):
#    sched={gto,lrr}  ocs=1..8  dp={4,8,12}
#    fixed: rfc=1 bank=2 wbd=1 reuse=0 regb=8 ocu=8
# 3. Workloads: 10 from the Rodinia suite (backprop/bfs/heartwall/hotspot/lud/nn/nw/pathfinder/srad_v2/streamcluster)
# 4. Parsing and plotting:
python3 script/analyze_oc_stall.py      # OC stall reason attribution
python3 script/analyze_reuse_stats.py   # reuse statistics
python3 script/analyze_case_cycles.py   # cycle comparison
```

Note: `reuse=0` means the actual RFC replacement behavior is unchanged; all reuse-related counters are bypass (observation-only) statistics, ensuring performance data and reuse data come from the same set of simulations.

## Methodology

Three-level progressive bottleneck localization: **stage-level stall distribution to narrow the scope → OC stall reason counters to locate the module → op-level decomposition + targeted resource sweep for controlled-variable validation**. See the two experiment reports for detailed discussion.

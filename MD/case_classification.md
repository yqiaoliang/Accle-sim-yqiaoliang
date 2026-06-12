# Rodinia Case 分类说明

本文档记录当前 Accel-Sim/GPGPU-Sim RFC 实验中 10 个 Rodinia case 的 workload 分类，便于后续分析 RFC/operand collector 数量、reuse、writeback depth、scheduler 等参数时分组对比。

## 分类依据

分类基于 baseline 配置的统计结果：

```text
regress_sched_gto_rfc1_bank2_wbd1_reuse0_ocs1_regb8_ocu8_20260610_013826
```

使用的统计文件：

```text
regress_result/20260610_013512/regress_sched_gto_rfc1_bank2_wbd1_reuse0_ocs1_regb8_ocu8_20260610_013826/confluence/case_op_stage_stall_remain.csv
```

主要判断指标：

- `LOAD_OP` 总 remain 占比
- `LOAD_OP` 在 `EXECUTION_PIPELINE` 阶段的 remain 占比
- compute op 总占比
- `SCHEDULER` / `OPERAND_COLLECTOR` / `EXECUTION_PIPELINE` / `WRITEBACK` 阶段占比

经验判断规则：

- 如果 `LOAD_OP` 总 remain 占比很高，或者 `LOAD_OP` 的 execution remain 占比很高，则归为 memory-bound。
- 如果 compute op 占比更高，并且 OC / scheduler / execution pipeline 对性能变化更敏感，则归为 mixed 或 compute-sensitive。
- 当前 10 个 case 中没有非常纯粹的 compute-bound case，`hotspot` 更适合作为 mixed / compute-sensitive case 分析。

## 当前 10 个 case 分类

| case | 建议分类 | LOAD 总 remain 占比 | LOAD execution remain 占比 | 主要特征 |
|---|---|---:|---:|---|
| `nn` | 强 memory-bound | 95.93% | 91.61% | 几乎完全由 LOAD 主导，memory latency 暴露最明显。 |
| `streamcluster` | 强 memory-bound | 94.49% | 88.66% | LOAD execution remain 极高，主要受 memory 行为影响。 |
| `nw` | 强 memory-bound | 88.02% | 84.77% | LOAD 主导，execution pipeline 中大量时间与访存相关。 |
| `lud` | memory-bound | 77.84% | 69.06% | LOAD 占主导，但仍有一定 compute 成分。 |
| `heartwall` | memory-bound | 74.29% | 71.68% | memory latency 明显，LOAD execution remain 高。 |
| `pathfinder` | memory-bound | 72.87% | 70.19% | memory latency 明显，适合观察访存瓶颈下 RFC 参数是否有效。 |
| `srad_v2` | memory-bound | 67.70% | 63.31% | LOAD execution remain 为主，compute 成分相对更高一些。 |
| `bfs` | memory-bound | 63.09% | 61.04% | irregular memory access 明显，访存行为主导。 |
| `backprop` | 偏 memory-bound / mixed | 63.50% | 55.02% | LOAD 较高，但 compute op 也有 36.50%，适合观察 memory 与 compute 混合瓶颈。 |
| `hotspot` | mixed，偏 compute-sensitive | 33.49% | 31.53% | compute op 占 66.51%，更适合观察 OC、scheduler、execution pipeline 的瓶颈转移。 |

## 推荐分组

### Memory-bound 组

```text
nn
streamcluster
nw
lud
heartwall
pathfinder
srad_v2
bfs
```

分析重点：

- RFC / operand collector 数量增加是否真的降低 `gpu_tot_sim_cycle`。
- 如果 OC 占比上升但总周期变化很小，说明主要瓶颈仍然在 memory latency，而不是 OC 数量。
- 重点看 `LOAD_OP` 的 `EXECUTION_PIPELINE` remain 是否下降。

### Mixed / compute-sensitive 组

```text
backprop
hotspot
```

分析重点：

- `OPERAND_COLLECTOR` 占比是否随 RFC / OC 数量增加而上升。
- `SCHEDULER`、`OPERAND_COLLECTOR`、`EXECUTION_PIPELINE` 之间是否发生瓶颈转移。
- `hotspot` 尤其适合用来分析 OC 数量、bank conflict、scheduler 策略、writeback depth 的影响。

## 后续分析建议

分析每一组新结果时，建议按下面顺序进行：

1. 固定 baseline，确认每次只改变一个变量，例如 ocs、reuse、wbd 或 scheduler。
2. 先看总性能：`gpu_tot_sim_cycle`，并归一化到 baseline。
3. 再看 stage ratio：`SCHEDULER`、`OPERAND_COLLECTOR`、`EXECUTION_PIPELINE`、`WRITEBACK`。
4. 按 op 分类看变化，尤其关注 `LOAD_OP`、`ALU_OP`、`SP_OP`、`DP_OP`、`SFU_OP`。
5. 如果怀疑 bank conflict，需要补充专门 counter，例如 bank conflict 次数、bank busy stall、collector ready but bank unavailable 等。

## 面试表达模板

可以这样描述：

> 我没有直接把所有 Rodinia benchmark 混在一起平均，而是先基于模拟器输出的 op-level 与 stage-level remain cycles 做 workload 分类。大部分 case 在当前输入规模下表现为 memory-bound，例如 `nn`、`streamcluster`、`nw` 的 LOAD execution remain 占比超过 80%。因此当 RFC / operand collector 数量增加时，即使 OC 阶段占比上升，总体性能改善也可能有限，因为主瓶颈仍然是 memory latency。相对地，`hotspot` 和 `backprop` 更适合观察 operand collector、scheduler 和 execution pipeline 之间的瓶颈转移。

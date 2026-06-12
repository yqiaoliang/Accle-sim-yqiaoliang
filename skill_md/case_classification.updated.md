# Rodinia Case 分类说明

本文档记录当前 Accel-Sim/GPGPU-Sim RFC 实验中 10 个 Rodinia case 的 workload 分类，便于后续分析 RFC、operand collector 数量、reuse、writeback depth、scheduler、dp 等参数时分组对比。

## 分类依据

当前分类基于两类数据交叉判断：

1. 模拟结果中的 op-level 指令数量统计：

```text
regress_result/20260612_064245/confluence/case_op_count.csv
```

2. trace 指令集中的 SASS opcode 组成：

```text
/Users/bytedance/Desktop/Accel-sim/traces/device-0/12.6
```

使用 `inst_stage.log` 中的 `pc` 与 `op` 统计每个 case 的 op 分类数量，再用 trace 文件把 PC 映射回具体 SASS opcode。这样可以避免只看 `LOAD_OP`、`DP_OP` 等粗粒度分类带来的误判。

需要特别注意：

- `LOAD_OP` 不一定都是 global load。它可能包含 `LDG.E`、`LDS` 等不同类型。`LDG.E` 更偏 global memory，`LDS` 更偏 shared memory，代价差异很大。
- `DP_OP` 不一定都是真正的 `DFMA` / `DMUL` / `DADD`。在部分 case 中，`DP_OP` 分类下可能混入 `MUFU.RCP`、`F2I`、`IADD3`、`IMAD` 等指令。
- 因此，判断 case 类型时不能只看 op 大类比例，还要看 trace opcode 组成和 stage cycle 分布。

## Trace 指令类型归类规则

本文档把 SASS mnemonic 粗分为以下类型：

| 类型 | 代表 opcode | 含义 |
|---|---|---|
| `load` | `LDG.*`, `LDS`, `LDL`, `LDC` | global/shared/local/constant load |
| `store` | `STG.*`, `STS`, `STL` | store |
| `dp_compute` | `DFMA`, `DMUL`, `DADD`, `DSETP` | 双精度计算 |
| `fp_convert_compute` | `FFMA`, `FMUL`, `FADD`, `F2F`, `F2I`, `I2F` | 单精度计算、浮点转换、整数/浮点转换 |
| `sfu_special` | `MUFU.*`, `RRO` | special function / reciprocal / transcendental 相关 |
| `int_addr_control` | `IADD3`, `IMAD`, `LOP`, `SHF`, `ISETP`, `LEA` | 整数计算、地址计算、predicate/control 辅助 |
| `move_predicate` | `MOV`, `S2R`, `SEL`, `PRMT` | move、predicate、寄存器辅助操作 |
| `control` | `BRA`, `EXIT`, `SSY`, `SYNC` | 控制流 |
| `other` | 其它未细分项 | 需要按具体 PC 再看 |

## 当前 10 个 case 的指令组成

| case | inst 数 | top op classes | trace type mix | top SASS mnemonics | 初步类型 |
|---|---:|---|---|---|---|
| `backprop` | 269,331 | `INTP_OP` 41.1%, `LOAD_OP` 24.7%, `ALU_OP` 22.1%, `DP_OP` 5.3%, `SP_OP` 3.8% | int/address 45.6%, load 18.4%, fp/convert 16.7%, move 6.8%, SFU 5.3% | `IADD3` 13.7%, `LDG.E` 9.3%, `IMAD` 9.1%, `LDS` 9.1%, `I2F.U32.RP` 8.4% | mixed，偏地址/整数 + memory |
| `bfs` | 109,367 | `INTP_OP` 77.2%, `LOAD_OP` 14.8%, `ALU_OP` 8.0% | int/address 74.7%, load 15.8%, move 8.0% | `IADD3` 23.2%, `IMAD.MOV.U32` 12.4%, `IADD3.X` 10.4%, `LDG.E` 9.0%, `LDG.E.U8` 6.8% | irregular/address-heavy memory |
| `heartwall` | 178,373 | `INTP_OP` 72.8%, `ALU_OP` 12.9%, `LOAD_OP` 12.9%, `SFU_OP` 1.4% | int/address 68.1%, load 17.5%, move 5.6%, fp/convert 2.7%, SFU 1.4% | `IADD3` 19.7%, `LDG.E` 12.9%, `IMAD` 12.1%, `IMAD.MOV` 10.8%, `IMAD.WIDE` 7.9% | address-heavy，轻 memory |
| `hotspot` | 600,596 | `INTP_OP` 32.3%, `ALU_OP` 19.7%, `LOAD_OP` 17.9%, `SP_OP` 15.4%, `DP_OP` 12.3% | int/address 29.9%, fp/convert 27.7%, load 17.9%, dp 12.3%, move 7.4% | `IADD3` 14.4%, `LDS` 13.5%, `F2F.F64.F32` 10.6%, `DADD` 7.0%, `FFMA` 6.6% | mixed compute，适合看 compute/OC/scheduler |
| `lud` | 23,130 | `LOAD_OP` 43.6%, `INTP_OP` 28.1%, `SP_OP` 21.9%, `ALU_OP` 5.8% | load 37.5%, int/address 35.5%, fp/convert 13.4%, move 1.9% | `LDS` 27.2%, `IADD3` 16.1%, `FFMA` 13.4%, `IMAD.WIDE.U32` 10.8%, `LDG.E` 10.2% | shared-memory/load-heavy mixed |
| `nn` | 582,497 | `LOAD_OP` 49.9%, `INTP_OP` 24.8%, `SP_OP` 16.7%, `ALU_OP` 7.2% | load 49.9%, int/address 24.8%, fp/convert 20.6% | `LDG.E.S8` 49.9%, `IMAD.MOV.U32` 10.5%, `FFMA` 8.4%, `IADD3` 5.4%, `I2FP.F32.S32` 5.2% | 强 global-load memory-bound |
| `nw` | 28,888 | `INTP_OP` 52.4%, `LOAD_OP` 45.4%, `ALU_OP` 2.2% | load 43.3%, int/address 39.5%, other 17.0% | `LDS` 30.7%, `IADD3` 19.6%, `LDG.E` 12.6%, `IMNMX` 10.7%, `IMAD.IADD` 7.4% | shared-memory + address-heavy，小规模 memory |
| `pathfinder` | 20,279 | `INTP_OP` 54.3%, `LOAD_OP` 32.9%, `ALU_OP` 12.8% | int/address 45.2%, load 32.9%, move 12.8% | `IADD3` 18.9%, `LDG.E` 18.0%, `LDS` 14.9%, `IMAD.MOV.U32` 12.0%, `PRMT` 10.5% | address + memory mixed |
| `srad_v2` | 223,264 | `INTP_OP` 37.2%, `LOAD_OP` 25.3%, `SP_OP` 20.4%, `ALU_OP` 9.7%, `DP_OP` 5.0% | int/address 35.6%, fp/convert 21.8%, load 16.0%, dp 4.1%, SFU 2.3% | `FFMA` 10.5%, `IADD3` 9.9%, `LDG.E` 9.8%, `LDS` 6.2% | balanced mixed，含真实 DP/FP 计算 |
| `streamcluster` | 972,590 | `LOAD_OP` 61.3%, `INTP_OP` 15.9%, `SP_OP` 15.0%, `ALU_OP` 7.8% | load 61.3%, int/address 15.9%, fp/convert 15.0%, move 7.8% | `LDG.E` 59.6%, `IMAD.WIDE` 8.1%, `FADD` 7.7%, `FFMA` 6.8%, `MOV` 6.1% | 强 global-load memory-bound |

## Case 逐项分析

### `streamcluster`

`streamcluster` 是最典型的 global memory load 主导 case。trace 中 `LDG.E` 占 59.6%，`LOAD_OP` 占 61.3%，说明它的 load 大部分是真正的 global load，而不是 shared load。这个 case 很适合观察 memory pipeline、L1D/L2、reservation fail、load execution remain 对性能的影响。

使用建议：

- 适合归入强 memory-bound 组。
- 当 RFC/OC 数量变化时，如果总 cycle 改善不明显，优先检查 memory latency 和 cache/port 压力，而不是只看 OC 阶段。
- 不适合用来单独评价 compute pipeline 优化。

### `nn`

`nn` 也非常 load-heavy，`LOAD_OP` 占 49.9%，trace 中 `LDG.E.S8` 直接占 49.9%。这说明它的访存指令非常集中，而且以 global byte/short 类 load 为主。它通常更受 memory latency、global access coalescing、cache 行为影响。

使用建议：

- 归入强 global-load memory-bound 组。
- 适合观察 global load 相关参数变化。
- 如果某个 config 对 `nn` 改善明显，需要重点确认是否降低了 load execution remain 或 memory stall。

### `nw`

`nw` 表面上 `LOAD_OP` 很高，占 45.4%，但 trace 显示 `LDS` 占 30.7%，`LDG.E` 只有 12.6%。因此它不是纯 global memory-heavy，而是 shared-memory + 地址计算主导。此前对比 `streamcluster` 时可以看到：`nw` 的 cache hit ratio 可能更低，但 global load 绝对数量很少，且大量 load 是 `LDS`，所以 LOAD_OP 总时间仍明显短。

使用建议：

- 归入 shared-memory/address-heavy mixed memory 组。
- 不应只用 L2 hit ratio 判断其 LOAD_OP 时间。
- 适合观察 shared memory、地址计算、scheduler/OC 对短 load 的影响。

### `lud`

`lud` 的 `LOAD_OP` 占 43.6%，trace 中 `LDS` 占 27.2%，`LDG.E` 占 10.2%，同时有 `FFMA` 和 `IMAD.WIDE.U32`。它是 shared-memory load 与计算混合的 case，不是纯 global-memory case。

使用建议：

- 归入 shared-memory/load-heavy mixed 组。
- 适合观察 OC、bank、shared load、writeback depth 的影响。
- 分析时应区分 `LDS` 和 `LDG.E`，不要把所有 LOAD_OP 都当 global memory latency。

### `pathfinder`

`pathfinder` 中 `INTP_OP` 占 54.3%，`LOAD_OP` 占 32.9%。trace 中 `IADD3`、`LDG.E`、`LDS`、`PRMT` 都比较明显，说明它是地址计算 + memory mixed 类型。它的输入规模较小，绝对指令数也较少。

使用建议：

- 归入 address + memory mixed 组。
- 适合观察地址计算、load、scheduler 间的瓶颈转移。
- 不建议只用 memory-bound 标签解释所有变化。

### `bfs`

`bfs` 的 `INTP_OP` 占 77.2%，trace 中 int/address 类占 74.7%。这符合 BFS irregular traversal 的特征：大量索引、地址计算、predicate/control 辅助，load 占比不算最高但访问可能不规则。

使用建议：

- 归入 irregular/address-heavy memory 组。
- 重点看地址计算、predicate、load latency 之间的交互。
- 如果 cache hit ratio 不高，不一定代表 LOAD_OP 数量主导；还要看 int/address 指令是否占主导。

### `heartwall`

`heartwall` 的 `INTP_OP` 占 72.8%，trace 中 int/address 类占 68.1%，`LDG.E` 占 12.9%。它主要是地址/整数辅助操作多，global load 次之，compute 比例不高。

使用建议：

- 归入 address-heavy，轻 memory 组。
- 适合观察 scheduler、operand collector、地址计算相关压力。
- 与强 memory-bound case 对比时，不应只看 LOAD_OP remain。

### `backprop`

`backprop` 是 mixed case：`INTP_OP` 41.1%，`LOAD_OP` 24.7%，`ALU_OP` 22.1%，并且有少量 `DP_OP`、`SP_OP`、`SFU_OP`。trace 显示它的主要指令包括 `IADD3`、`LDG.E`、`IMAD`、`LDS`、`I2F.U32.RP`。需要注意，`backprop` 中 `DP_OP` 分类下的大头并不是真正的 `DFMA/DMUL/DADD`，而是 `IADD3`、`MUFU.RCP`、`IMAD`、`F2I` 等指令，因此不能简单把 `DP_OP` 当成纯双精度计算。

使用建议：

- 归入 mixed，偏地址/整数 + memory。
- 适合观察 OC、scheduler、memory、SFU/convert 之间的瓶颈转移。
- 分析 `DP_OP` 时必须映射 PC 到 trace opcode。

### `srad_v2`

`srad_v2` 是比较 balanced 的 mixed case。它有 `INTP_OP` 37.2%、`LOAD_OP` 25.3%、`SP_OP` 20.4%、`DP_OP` 5.0%。trace 中 `FFMA`、`IADD3`、`LDG.E`、`LDS` 都较明显，并且 `DP_OP` 中确实有 `DFMA`、`DMUL`、`DADD` 等真正的双精度计算。此前对比 `backprop` 时可以看到，`srad_v2` 的 DP_OP execution pipeline 较短，原因之一是具体 opcode 组成不同，大量 DP 指令落在较短路径。

使用建议：

- 归入 balanced mixed，含真实 DP/FP compute。
- 适合观察 compute pipeline、DP pipeline、scheduler/OC 的综合影响。
- 与 `backprop` 对比时，应强调两者的 `DP_OP` 具体 opcode 不同。

### `hotspot`

`hotspot` 是当前 10 个 case 中最适合观察 compute/OC/scheduler 的 case。它的 `LOAD_OP` 只有 17.9%，而 `SP_OP` + `DP_OP` + `ALU_OP` 合计较高。trace 中 `FFMA`、`F2F.F64.F32`、`DADD`、`LDS`、`IADD3` 都明显，属于计算与 shared-memory 混合。

使用建议：

- 归入 mixed compute-sensitive 组。
- 适合观察 OC 数量、bank conflict、scheduler 策略、writeback depth、dp 参数对性能的影响。
- 如果某个参数只在 `hotspot` 上明显改善，通常说明它更影响 compute/OC/scheduler，而不是纯 memory latency。

## 推荐分组

### 强 global-load memory-bound

```text
streamcluster
nn
```

特点：

- `LDG.E` / `LDG.E.S8` 占比很高。
- LOAD_OP 大多是真正 global load。
- 适合观察 memory latency、L1D/L2、reservation fail、load execution remain。

### Shared-memory / load-heavy mixed

```text
nw
lud
pathfinder
```

特点：

- LOAD_OP 占比较高，但 `LDS` 占比也高。
- 不能把 LOAD_OP 全部解释为 global memory latency。
- 适合观察 shared load、地址计算、OC/scheduler、bank 相关行为。

### Irregular / address-heavy

```text
bfs
heartwall
```

特点：

- `INTP_OP` 和 int/address 类 SASS 占主导。
- 访问可能不规则，但总体瓶颈不一定只来自 LOAD_OP。
- 适合观察地址计算、predicate、scheduler 压力。

### Balanced mixed / compute-sensitive

```text
backprop
srad_v2
hotspot
```

特点：

- compute、load、address 指令都有明显占比。
- 适合观察 RFC、OC、scheduler、writeback depth、dp 参数带来的瓶颈转移。
- 分析 `DP_OP` 时必须映射具体 PC/opcode，不能只看 op 大类。

## 分析建议

分析新结果时建议按下面顺序：

1. 先看总性能：`gpu_tot_sim_cycle`，并归一化到 baseline。
2. 看 case 的 trace 类型：global load、shared load、int/address、FP/DP compute 哪个占主导。
3. 再看 stage ratio：`SCHEDULER`、`OPERAND_COLLECTOR`、`EXECUTION_PIPELINE`、`WRITEBACK`。
4. 按 op 分类看变化，尤其关注 `LOAD_OP`、`INTP_OP`、`SP_OP`、`DP_OP`。
5. 对可疑 case 做 PC 级 trace 映射，确认 `LOAD_OP` 到底是 `LDG.E` 还是 `LDS`，`DP_OP` 到底是 `DFMA/DMUL/DADD` 还是其它被归类进来的指令。
6. 如果怀疑 bank conflict，需要补充专门 counter，例如 bank conflict 次数、bank busy stall、collector ready but bank unavailable 等。

## 面试表达模板

可以这样描述：

> 我没有直接把所有 Rodinia benchmark 混在一起平均，而是先基于 `inst_stage.log` 的 op-level/stage-level 统计做 workload 分类，再把 PC 映射回 trace 中的 SASS opcode。这样可以区分 `LOAD_OP` 中的 global load 和 shared load，也能发现 `DP_OP` 并不总是纯双精度指令。比如 `streamcluster` 和 `nn` 是强 global-load memory-bound，`nw` 和 `lud` 更偏 shared-memory/load-heavy mixed，`bfs` 和 `heartwall` 是 address-heavy，而 `hotspot`、`srad_v2`、`backprop` 更适合观察 compute、operand collector、scheduler 和 writeback depth 之间的瓶颈转移。

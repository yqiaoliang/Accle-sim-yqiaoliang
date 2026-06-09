# 回归结果分析流程：参数 sweep 与 case ratio 对比

本文档用于指导分析 Accel-Sim/GPGPU-Sim 回归结果目录中的多参数实验结果。示例数据目录：

```text
/Users/bytedance/Desktop/Accel-sim/accel-sim-framework/regress_result/20260609_030436
```

核心目标不是只找“总周期最小”的配置，而是系统回答以下问题：

1. 哪个参数组合整体最好？
2. 哪些参数带来稳定收益？
3. 哪些参数只对少数 case 有收益，甚至会让其它 case 退化？
4. 收益主要来自哪些 benchmark？
5. 性能变化能否被 stage/op stall 分解解释？
6. 最终推荐哪个配置作为默认配置，为什么？

---

## 1. 确认数据完整性

首先确认结果目录下有多少个配置、每个配置有多少个 case。

重点检查文件：

```text
<result_dir>/confluence/config_case_gpu_tot_sim_cycle.csv
<result_dir>/*/confluence/case_gpu_tot_sim_cycle.csv
<result_dir>/*/confluence/case_op_stage_stall_remain.csv
<result_dir>/*/confluence/case_op_remain_cycles.csv
```

其中：

- `config_case_gpu_tot_sim_cycle.csv`：跨配置、跨 case 的总表，是主分析入口。
- `case_gpu_tot_sim_cycle.csv`：单个配置下所有 case 的 `gpu_tot_sim_cycle`。
- `case_op_stage_stall_remain.csv`：按 case/op/stage 拆分 stall 与 remain cycle，用于解释原因。
- `case_op_remain_cycles.csv`：按 op/stage 统计 remain cycle 的均值和中位数，用于观察某类 op 是否变慢。

需要确认：

- 每个配置是否都有相同数量的 case。
- 是否存在缺失 `.log` 或缺失 `gpu_tot_sim_cycle` 的 case。
- 不同配置是否真的来自同一组 benchmark，而不是混入旧结果。
- 日志路径是否指向当前回归目录，而不是历史 stale log。

---

## 2. 解析配置名中的参数

回归目录名一般包含参数信息，例如：

```text
regress_sched_gto_rfc1_bank2_wbd2_reuse0_ocs2_regb8_ocu8_20260609_033700
```

需要解析出：

| 参数 | 含义 |
| --- | --- |
| `sched` | scheduler，例如 `gto` / `lrr` |
| `rfc` | RFC 是否启用，`0` 或 `1` |
| `bank` | bank 参数 |
| `wbd` | writeback/depth 相关参数 |
| `reuse` | reuse 是否启用 |
| `ocs` | operand collector 相关参数 |
| `regb` | register bank 参数 |
| `ocu` | operand collector unit 数量 |

分析时不要只按目录名字符串排序，应该先解析参数，再按参数维度做对比。

---

## 3. 建立 baseline

至少需要建立以下几类 baseline。

### 3.1 原始 baseline

通常使用 RFC 关闭的配置，例如：

```text
sched=gto, rfc=0, ocu=8
sched=lrr, rfc=0, ocu=8
```

用于回答：RFC 打开后整体是否有效。

### 3.2 最优 baseline

每个 case 取所有配置中 cycle 最小的配置作为 baseline。

用于回答：每个配置离理论最优还有多远。

### 3.3 自选参数组合 baseline

在 dashboard 中选择任意一个完整配置作为 baseline，例如：

```text
gto_rfc1_bank2_wbd1_reuse0_ocs2_regb8_ocu8
```

然后查看所有 case、所有其它配置相对它的 ratio：

```text
ratio = current_cycles / baseline_cycles
```

解释方式：

- `ratio < 1.0`：当前配置比 baseline 快。
- `ratio = 1.0`：与 baseline 相同。
- `ratio > 1.0`：当前配置比 baseline 慢。

### 3.4 单参数 baseline

固定其它参数不变，只改变某一个参数。例如选择：

```text
baseline parameter = ocs
baseline value = 1
```

然后比较 `ocs=2` 相对 `ocs=1` 的变化。

这种分析适合回答某个参数本身是否稳定有效。

---

## 4. 主指标分析：gpu_tot_sim_cycle

主指标使用：

```text
gpu_tot_sim_cycle
```

建议计算以下统计量：

1. 每个配置的总 cycle：

```text
total_cycles = sum(gpu_tot_sim_cycle over all cases)
```

2. 每个配置的几何平均 speedup：

```text
geo_speedup = geometric_mean(baseline_cycle / current_cycle)
```

3. 每个配置相对 baseline 的总周期比例：

```text
total_ratio = sum(current_cycles) / sum(baseline_cycles)
```

4. 每个 case 的 ratio：

```text
case_ratio = current_case_cycle / baseline_case_cycle
```

总 cycle 适合看整体吞吐，几何平均适合避免大 case 完全主导结论。两者都要看。

---

## 5. 排名分析

先按总 cycle 排序，得到整体最优配置。

但不要只停留在排名，需要继续拆解：

- 第一名和第二名差距是否很小？
- 如果差距小于 0.1%，可能属于噪声级别，不能过度解读。
- 最优配置是否对多数 case 都有收益？
- 还是只因为某个大 case 收益很大而排第一？

示例判断：

```text
如果 wbd1 与 wbd2 总 cycle 只差几百 cycles，而总量接近百万级，说明 wbd 不是主导参数。
```

---

## 6. 成对参数影响分析

这是参数 sweep 分析中最重要的一步。

原则：只改变一个参数，其它参数保持完全一致。

例如分析 `ocs`：

```text
sched=gto, rfc=1, wbd=1, reuse=0, ocs=1
vs
sched=gto, rfc=1, wbd=1, reuse=0, ocs=2
```

计算：

```text
change_pct = (cycle_ocs2 / cycle_ocs1 - 1) * 100%
```

对以下参数分别做成对比较：

- `ocs=2` vs `ocs=1`
- `reuse=1` vs `reuse=0`
- `wbd=2` vs `wbd=1`
- `sched=lrr` vs `sched=gto`
- `ocu=8` vs `ocu=4`，如果数据中存在
- `rfc=1` vs `rfc=0`

判断标准：

- 多数组合都变快：稳定正收益。
- 多数组合都变慢：稳定负收益。
- 有些快、有些慢：需要按 case 或 stage 分解继续分析。
- 差异极小：可能不是主导参数。

---

## 7. Case 贡献分析

总 cycle 往往会被大 case 主导，所以必须分析每个 case 的贡献。

对某个候选配置和 baseline，计算每个 case 的绝对变化：

```text
delta_cycles = current_case_cycle - baseline_case_cycle
```

和相对变化：

```text
delta_pct = (current_case_cycle / baseline_case_cycle - 1) * 100%
```

需要重点回答：

1. 总收益主要来自哪些 case？
2. 哪些 case 退化最明显？
3. 是否存在“小 case 大比例退化，但大 case 小比例收益导致总周期仍下降”的情况？
4. 推荐配置是否会牺牲某些重要 benchmark？

分析输出建议包含：

| case | baseline cycle | current cycle | delta cycle | delta % |
| --- | ---: | ---: | ---: | ---: |
| streamcluster | ... | ... | ... | ... |
| backprop | ... | ... | ... | ... |

---

## 8. Scheduler 分析

如果同时有 `gto` 和 `lrr`，需要分别建立 baseline。

推荐比较：

1. `lrr rfc0` vs `gto rfc0`
2. `lrr rfc1` vs `gto rfc1`
3. 各自 scheduler 内部的 RFC 收益

不要直接把所有 GTO/LRR 配置混在一起下结论，因为 scheduler 可能改变整体行为。

应该回答：

- RFC 是否缩小了 GTO 和 LRR 的差距？
- 哪个 scheduler 更适合作为最终配置？
- 某些参数是否只在 GTO 或只在 LRR 下有效？

---

## 9. Stage/op 分解分析

当总 cycle 发生变化后，需要用 stage/op 数据解释原因。

主要看：

```text
case_op_stage_stall_remain.csv
```

按以下维度聚合：

1. 按 stage 聚合 stall：

```text
sum(stall) by stage
```

2. 按 op 聚合 stall：

```text
sum(stall) by op
```

3. 按 case 聚合 stall：

```text
sum(stall) by case
```

重点关注 stage：

- `SCHEDULER`
- `OPERAND_COLLECTOR`
- `EXECUTION_PIPELINE`
- `WRITEBACK`
- memory/load 相关 stage

如果某配置总 cycle 下降，但某个 stage stall 上升，需要解释为“瓶颈转移”，而不是简单说所有方面都改善。

示例结论格式：

```text
RFC 后 SCHEDULER stall 明显下降，但 OPERAND_COLLECTOR stall 上升，说明 RFC 减少了 scheduler 侧等待，同时把压力转移到了 operand collector/load 路径。最终是否值得采用，要以 gpu_tot_sim_cycle 和 case ratio 为准。
```

---

## 10. 异常检查

需要检查以下异常：

1. 某个配置只有部分 case。
2. 某个 case 的 cycle 为 0 或异常小。
3. 某个配置的日志时间明显早于当前回归时间。
4. `.log` 文件来自 wrapper log 而不是真正 simulator log。
5. stage/op CSV 只覆盖部分配置，不能用于所有配置的原因解释。
6. 某个参数组合理论上应存在，但结果目录缺失。

如果 stage/op 分解文件缺失，不要强行解释该配置的微观原因，只能基于 `gpu_tot_sim_cycle` 给出宏观结论。

---

## 11. Dashboard 使用方法

使用脚本生成 dashboard：

```bash
python3 /Users/bytedance/Desktop/Accel-sim/accel-sim-framework/script/cycle_dashboard.py \
  /Users/bytedance/Desktop/Accel-sim/accel-sim-framework/regress_result/20260609_030436
```

生成文件：

```text
<result_dir>/confluence/cycle_dashboard.html
```

推荐使用的模式：

### 11.1 Config A vs Baseline

用于比较两个完整配置在所有 case 上的差异。

适合回答：配置 A 是否比配置 B 更好。

### 11.2 All configs vs selected baseline config

用于选择某个完整参数组合作为 baseline，并查看其它所有配置相对它的 ratio。

适合回答：某个候选默认配置是否稳健。

### 11.3 All configs vs selected parameter baseline

用于选择某个参数和值作为 baseline，例如 `ocs=1`，然后比较其它参数值。

适合回答：单个参数是否有稳定收益。

### 11.4 All configs vs best per case

用于查看每个配置距离每个 case 的最优结果有多远。

适合回答：候选配置是否接近 per-case 最优。

### 11.5 All configs vs lrr/rfc0/ocu8

用于和固定历史 baseline 对比。

适合回答：相对传统 baseline 是否有提升。

---

## 12. 推荐结论写法

最终分析报告建议包含以下结构。

### 12.1 Summary

简要说明：

- 数据目录
- 配置数量
- case 数量
- 主指标
- 最优配置

### 12.2 Overall ranking

列出总 cycle 前几名。

说明第一名和第二名是否差距显著。

### 12.3 Parameter effect

逐个参数给结论：

```text
ocs=2：稳定正收益
reuse=1：多数情况下负收益
wbd=2：影响较小
sched=gto：整体优于 lrr
```

每个结论都需要有成对比较数据支持。

### 12.4 Case-level behavior

说明：

- 最大收益 case
- 最大退化 case
- 总收益是否由少数 case 主导

### 12.5 Stage/op explanation

说明主要 stall 变化：

- 哪些 stage 下降
- 哪些 stage 上升
- 是否发生瓶颈转移

### 12.6 Recommendation

给出推荐配置，例如：

```text
sched=gto, rfc=1, bank=2, wbd=1, reuse=0, ocs=2, regb=8, ocu=8
```

同时说明理由：

- 整体 cycle 接近最优或最优。
- 参数收益稳定。
- 没有严重 case 退化，或退化可接受。
- 如果某个参数差异很小，选择更保守、更简单的值。

---

## 13. 常用判断原则

1. **先看总 cycle，再看几何平均，再看 case ratio。**
2. **不要只根据总排名推荐配置。** 大 case 可能掩盖小 case 退化。
3. **成对比较时只能改变一个参数。** 否则不能归因。
4. **stage/op 分解只能解释已有数据，不要用于缺失配置。**
5. **小于 0.1% 的差异要谨慎解读。** 可能属于噪声或仿真波动。
6. **如果性能提升伴随瓶颈转移，要明确写出来。**
7. **最终推荐要兼顾整体收益、稳定性和可解释性。**

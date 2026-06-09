# Accel-Sim `inst_stage.log` 分析脚本需求上下文

## 背景

当前 Accel-Sim 回归/单次运行结果会整理到 `accel-sim-framework/regress_result/` 下。一次回归通常对应一个 `$time` 目录，例如：

```text
/Users/bytedance/Desktop/Accel-sim/accel-sim-framework/regress_result/20260608_112254
```

每个 `$time` 目录下面可能有多个 config 参数组合目录，每个 config 目录下面又有多个 case 目录。case 目录中通常包含：

```text
<case>/
  <case>.log
  inst_stage.log
  regress.config
```

需要一个独立分析脚本读取已经跑完的结果目录，解析所有 `inst_stage.log`，并生成 CSV 和图。分析流程需要和 regression/result 生成流程分开：结果跑完后，手动设置或传入结果路径，再运行分析脚本。

当前分析脚本路径：

```text
/Users/bytedance/Desktop/Accel-sim/accel-sim-framework/script/analyze_inst_stage.py
```

脚本顶部有可手动修改的路径变量：

```python
result_path = "..."
```

也可以命令行传参覆盖：

```bash
python3 script/analyze_inst_stage.py /path/to/regress_result/<time>
python3 script/analyze_inst_stage.py 20260608_112254
python3 script/analyze_inst_stage.py --no-graphs 20260608_112254
```

如果只传 `$time`，脚本应自动解析为 `accel-sim-framework/regress_result/$time`。

## 解析对象和统计口径

输入文件是每个 case 目录下的：

```text
inst_stage.log
```

可以参考旧脚本和旧结果格式：

```text
/Users/bytedance/Desktop/Accel-sim/parse_inst_stats.py
/Users/bytedance/Desktop/Accel-sim/stats_combined.csv
```

stage 关注这些阶段：

```text
SCHEDULER
OPERAND_COLLECTOR
EXECUTION_PIPELINE
WRITEBACK
```

`NONE` 不参与主要图表统计。

每条 inst 记录按 `warp_id / pc / op` 解析，并统计各 stage 的：

```text
stall
remain
```

op 的 cycle/latency 统计口径是：

```text
各 stage 的 remain cycles
```

op 的 total cycle/latency 是：

```text
SCHEDULER remain
+ OPERAND_COLLECTOR remain
+ EXECUTION_PIPELINE remain
+ WRITEBACK remain
```

不是 stall + remain。

## 输出层级 1：每个 case 目录

对于每个包含 `inst_stage.log` 的 case，在 case 同层目录生成：

```text
inst_stage_result.csv
inst_stage_graph/
```

### `inst_stage_result.csv`

CSV 需要包含：

1. warp 维度的 stall 表
2. op 维度的 stall 表
3. warp 维度的 remain 表
4. op 维度的 remain 表
5. op 在不同 stage 的 remain cycle 平均值和中位数
6. op 的 TOTAL remain cycle 平均值和中位数

比例需要按当前 row 内各 stage 的总和计算。

### `inst_stage_graph/` 图片

每个 case 需要生成这些图：

```text
warp_stage_stall_ratio.png
warp_stage_remain_ratio.png
op_stage_stall_ratio.png
op_stage_remain_ratio.png
op_stage_latency_avg_median.png
```

图表要求：

- warp 图可以多个 warp 放在同一张图里。
- op 图不要把不同 op 类型混在同一组柱状图里，因为不同 op 差异很大。
- op 图应采用“一个 op 一个子图”的形式：
  - 一个 op 对应一个 subplot
  - 子图内部比较该 op 的不同 stage
  - 多个 op 子图纵向组合到同一张 PNG
  - 图片可以很长，向下滚动查看不同 op
- `op_stage_latency_avg_median.png` 中，每个 op 一个子图，子图内展示各 stage 和 TOTAL 的 avg/median remain cycles。
- 所有柱状图都尽量在柱子上方或右侧标出数值，方便直接读数和比较差异。

## 输出层级 2：每个 config 参数组合目录的 `confluence/`

每个 config 参数组合目录下包含多个 case。需要在该 config 目录下生成：

```text
<config>/confluence/
```

这个 confluence 汇总该 config 下的所有 case。

### 图片

需要生成：

```text
case_stage_stall_ratio.png
case_stage_remain_ratio.png
case_op_avg_remain_cycles.png
case_op_median_remain_cycles.png
op_stage_stall_ratio.png
op_stage_remain_ratio.png
```

要求：

1. `case_stage_stall_ratio.png` / `case_stage_remain_ratio.png`
   - 每个 case 把所有 warp 的各 stage stall/remain 相加。
   - 展示不同 case 的 stage stall/remain ratio。
   - config 内 confluence 的 case label 用 case 名按 `-` 分割后的第一个字符串即可，例如 `bfs-rodinia...` 显示为 `bfs`。

2. `case_op_avg_remain_cycles.png` / `case_op_median_remain_cycles.png`
   - 统计不同 case 的不同 op 的 TOTAL remain cycles 的平均值/中位数。
   - 不同 op 也不要混在一张柱状图里。
   - 采用“一个 op 一个子图”，每个子图中比较不同 case。

3. `op_stage_stall_ratio.png` / `op_stage_remain_ratio.png`
   - 在该 config 的所有 case 范围内，按 op 类型汇总。
   - 展示不同 op 在不同 stage 的 stall ratio 和 remain ratio。
   - 也是“一个 op 一个子图”，子图内比较 stage。

4. 所有柱状图尽量带数值标签。

### CSV

需要生成：

```text
case_op_stage_stall_remain.csv
case_op_remain_cycles.csv
```

含义：

- `case_op_stage_stall_remain.csv`：不同 case、不同 op、不同 stage 的 stall/remain 数值和比例。
- `case_op_remain_cycles.csv`：不同 case、不同 op、不同 stage/TOTAL 的 avg/median remain cycles。

## 输出层级 3：整个 `$time` 结果目录的 root `confluence/`

对于一个 `$time` 结果目录，需要在根目录下生成：

```text
<time>/confluence/
```

这个 root confluence 汇总不同 config 参数组合。它可以参考“每个 config 的 confluence”，但是统计粒度变为：

```text
一个 config = 该 config 下所有 case 的总和或平均值
```

### 图片

需要生成：

```text
config_stage_stall_ratio.png
config_stage_remain_ratio.png
config_op_avg_remain_cycles.png
config_op_median_remain_cycles.png
op_stage_stall_ratio.png
op_stage_remain_ratio.png
```

要求：

1. `config_stage_stall_ratio.png` / `config_stage_remain_ratio.png`
   - 每个 config 汇总其所有 case。
   - 展示不同 config 参数组合的 stage stall/remain ratio。
   - root 级 config label 保留完整 config 参数名，方便区分参数组合。

2. `config_op_avg_remain_cycles.png` / `config_op_median_remain_cycles.png`
   - 每个 config 汇总其所有 case 后，统计不同 op 的 TOTAL remain cycles 平均值/中位数。
   - 不同 op 一个子图，每个子图比较不同 config。

3. `op_stage_stall_ratio.png` / `op_stage_remain_ratio.png`
   - 在整个 `$time` 目录所有 config/case 范围内，按 op 类型汇总。
   - 展示不同 op 在不同 stage 的 stall ratio 和 remain ratio。
   - 一个 op 一个子图。

4. 所有柱状图尽量带数值标签。

### CSV

需要生成：

```text
config_op_stage_stall_remain.csv
config_op_remain_cycles.csv
```

含义：

- `config_op_stage_stall_remain.csv`：不同 config、不同 op、不同 stage 的 stall/remain 数值和比例。
- `config_op_remain_cycles.csv`：不同 config、不同 op、不同 stage/TOTAL 的 avg/median remain cycles。

## 运行和验证约定

- 这个脚本只分析已有结果，不需要在 Docker 里运行；可以在宿主机直接跑。
- 如果只是检查语法：

```bash
cd /Users/bytedance/Desktop/Accel-sim/accel-sim-framework
python3 -m py_compile script/analyze_inst_stage.py
```

- 如果要完整分析当前 `result_path`：

```bash
python3 script/analyze_inst_stage.py
```

- 如果指定结果目录：

```bash
python3 script/analyze_inst_stage.py /Users/bytedance/Desktop/Accel-sim/accel-sim-framework/regress_result/temp
```

- 如果环境没有 matplotlib，可以只生成 CSV：

```bash
python3 script/analyze_inst_stage.py --no-graphs /path/to/result
```

## 当前实现状态

截至目前，`script/analyze_inst_stage.py` 已实现：

- 手动 `result_path = "..."`
- 命令行路径覆盖
- 每 case CSV 和图
- 每 config `confluence/`
- root `$time/confluence/`
- op 图按“一个 op 一个子图”纵向长图输出
- 柱状图数值标签
- config 内 confluence 的 case label 缩短为 `-` 前第一段
- root confluence 的 config label 保留完整参数名

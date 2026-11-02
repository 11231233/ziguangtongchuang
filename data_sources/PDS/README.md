# 干净源码工程（未构建过）

目录：`F:\wancheng_ziguang_jibian_codex`

**这个工程从来没跑过**——没有综合网表、没有布局布线结果、没有比特流、没有日志。
只有源码、仿真、约束，和一个只写了文件清单的工程文件。

## 内容

```
wancheng_ziguang_jibian_codex\
├─ wancheng_ziguang_jibian_codex.pds   工程文件（118 个条目，全是相对路径）
├─ rtl\                                源码 1.68 MB
│   ├─ top\ cam\ video\ warp\ mem\ ddr\ hdmi\ common\
│   └─ ip\   PLL / DDR3 / RAM（含 57 个 .vp）
├─ constr\                             board_pins.fdc / ddr3_pins.fdc / timing.fdc
├─ sim\
│   ├─ tb\     测试平台
│   └─ model\  存储模型、传感器模型等
└─ UNUSED_REMOVED.txt                  删掉的 15 个文件清单
```

共 **223 个文件**。

## 打开

PDS → **File → Open Project** → 选

```
F:\wancheng_ziguang_jibian_codex\wancheng_ziguang_jibian_codex.pds
```

器件已配好：**Logos / PGL50H / −6 / FBG484**，顶层 `top_pangu50`。

工程里 `.pds` 用的全是相对路径（`rtl/...`、`constr/...`），所以整个目录可以整体搬走。

## 第一次跑的六步（含 Compile）

| 步 | 面板项 | 参考耗时 |
|---|---|---|
| 1 | **Compile** | 约 1 分 |
| 2 | Synthesize | 2–3 分 |
| 3 | Device Map | 2–3 分 |
| 4 | Place & Route | 4–6 分 |
| 5 | Generate Bitstream | 1–2 分 |
| 6 | Download | 十几秒 |

⚠️ **必须先 Compile**。这一步把源码装载进工程数据库（生成 `compile/top_pangu50_comp.adf`），
后面每一步都依赖它。跳过直接点 Synthesize 会报：

```
E: Flow-0002: File '.../compile/top_pangu50_comp.adf' doesn't exist.
```

这不是代码问题，按顺序跑一遍就好。

### 跑完应该看到（同一份源码、seed=2 的历史实测值）

| 项 | 参考值 |
|---|---|
| `clk_pix` | WNS **2.666 ns**，0 失败端点 |
| `cam_pclk` | WNS 4.400 ns，0 失败端点 |
| `sys_clk` | WNS 12.375 ns，0 失败端点 |
| LUT | 8562 / 25800（**34%**） |
| DRM | 33.5 / 134（**25%**） |
| APM | 54.5 / 84（**65%**） |

布板结果有随机性，时序数字会有小幅浮动；**只要 WNS 为正、失败端点为 0 就正常**。
资源占用应当一致（±几十个 LUT）。

### 综合时的警告

会看到一些 `W: Loop was found during constant probe`，**属正常现象，可以忽略**。

## 仿真

仿真不在 PDS 里做——测试平台用了 iverilog 的专有参数，PDS 自带仿真器跑不了。

`sim\` 下是测试平台和模型，驱动脚本在可复现包里：

```powershell
cd F:\codex_ziguang\c1_verified_259C3381

# 整帧比对，0°，并模拟这块板子的 DDR 延迟
python scripts\verify_margin_corrected_frame_lut.py --angle 0 --ddr-latency 22

# 查找表 2099 组向量
python scripts\verify_radial_lut.py
```

`--ddr-latency 22` 是按这块板实测的 DDR 行为标定的值：仿真在 22 时算出的整帧时间
（26.4 ms）与板上 OSD 的 `CALC` 读数一致。

**推荐流程**：改 RTL → iverilog 仿真逐位一致 → PDS 综合布板 → 下载 → 看 OSD。

## 关于删掉的 15 个文件

它们都被 PDS 列为独立根（没有任何模块实例化），依赖分析也确认从 `top_pangu50`
不可达。详见 `UNUSED_REMOVED.txt`。

`ip\` 下的文件**全部保留**——那是 DDR3/PLL 库的内部实现，靠实例化名做可达性分析不可靠。

## 下载注意

- 调试选 **SRAM**（断电失效），演示选 **Flash**（断电保留）
- 生成的比特流在 `generate_bitstream\top_pangu50.sbit`
- 功能等同已验证的 `runtime_gamma_259C3381`（镜像修复 + 畸变矫正 + 自适应 Gamma）

# 紫光同创 FPGA 实时畸变矫正

当前主版本为 `wancheng_ziguang_jibian_codex` 的16×16输出分块工程。本仓库用于整理源码、当前固件和数据出处，未修改标定参数、LUT、畸变模型、插值算法或传感器几何配置。

## 当前版本与指标

- FPGA：PGL50H / -6 / FBG484，开发板MES50HP。
- 采集1296×972 RGB565；输出1280×720@60Hz。60Hz是HDMI扫描频率，不是新帧处理率。
- 当前传感器配置源帧率约22fps；实板CALC由用户确认约26～28ms。
- ±20°、1°步进、41档；支持RAW/COR、冻结和Gamma。串口系数、Zoom、强度及画质循环未接通，不列作已实现功能。
- 原GUI固件：`firmware/top_pangu50.sbit`，SHA256：`47b43f71cbda3bf63dd16e16297099ce8aecd916b6e1726e8db95007cbf36046`。
- 原GUI报告：WNS最小1.498ns、WHS最小0.191ns，失败端点0。此为历史构建报告，不冒充本目录重新构建的结果。
- 训练/验证残差0.8223/0.9467px；完整出处见data_sources。
- 视频18组端到端秒表差：中位105ms、均值约108.3ms、样本80～140ms，未经卷帘修正；不能保证稳定低于100ms。此前14ms解释撤回。

## 目录

|路径|是什么|
|---|---|
|rtl / constr / sim|当前GUI版完整RTL、约束、仿真平台和模型，含原厂IP|
|scripts / tools|配套构建、标定和验证工具|
|calib / targets / results|原标定产物、采集配置与相关结果|
|firmware|当前GUI构建固件，不是32×32测试版|
|reports/original_gui|当前版本的原始资源、时序和构建记录|
|data_sources|全部解压后的数据出处、38张原始标定帧、MTF、延迟视频与读数、电路参考；不含机械工程图|
|provenance|导入前原始顶层、工程文件和源码哈希，用来核对只做了ROM路径迁移|
|docs|参考Word，仍有早期版本称谓，以本README和data_sources/00_资料索引.md为准|
|local_archives|本机保留的完整数据出处ZIP，不纳入Git；解压内容已包含在data_sources|

## 构建与验证

原工程路径写死在顶层的ROM文件名已改为相对路径，数据内容不变。运行 `python scripts/build.py --name desktop_build --seed 2` 可在build目录生成独立快照，脚本会把快照ROM路径设置为本次构建路径。需安装PDS，默认查找D:/PDS/bin/pds_shell.exe，可通过PDS_SHELL环境变量指定。

GUI入口为 `ziguangtongchuang.pds`，清除了旧输出状态。请从项目根目录打开，依次Compile、Synthesize、Device Map、Place & Route、Generate Bitstream。原始GUI工程存于provenance，仅供追溯。

验证标定：`python tools/verify_calib_chain.py`。验证导入一致性：`python scripts/verify_source_import.py`。Python工具依赖numpy、opencv-python、Pillow等；跨机器重跑数据脚本还需按来源清单核对原绝对数据路径。

## 数据与版权

先读 `data_sources/00_资料索引.md` 和 `data_sources/00_证据对应表.csv`。部分历史记录仍有旧措辞，以索引中的版本更正为准。所有源码和资料保留原有版权声明；厂商IP、手册与第三方资料按各自条款使用。本仓库未为第三方内容添加MIT等统一开源许可证。

# 工作流包验证 · 2026-10-08

## 来源基线与行为测试

- 真实项目的失败基线见references/lessons.md：早期最近帧选图、白阈值、包围框花瓣污染，以及字幕首轮cel/字框/阴影/气泡错误；后续编码切点和透明淡出失败。不是虚构一个代理失败来满足流程。
- 独立Agent无技能基线对多数风险判断正确，但零trim案例的表述未排除坐标歧义。非零clipPos变体再次确认：pos960+note720=1680tick，不减clipPos480。
- 独立Agent加载技能后处理了24fps新任务、48kHz多窗口lag−240/−242/−241、含有效人声尾音、非零clipPos和无生成工具情形；给出按段回用姿势、保护人物、补241样点而不变速、保留尾音及能力范围声明。
- 试用指出“示例可能当成生产数据”和“FFmpeg -t例子可能截断有效尾音”两项缺口。修复前机械检查输出缺少example_only标志，基线失败已观察；修复后新增显式标志及--reject-example，并明确有效尾音处置。独立Agent只读复核确认两项缺口已处理。

## 可运行校核

1. pv_tools.py self-test通过：缺末帧被拒绝、A→B→A合法、1680tick换算正确、示例工程生产拒绝、提前/延后信号的lag及反号建议正确。
2. 清单示例结构检查通过，明确example_only=true、ready_to_render=false、asset_files_checked=false，不把schema通过冒充可渲染。
3. 用实际v10/v11成片检验compare-video --decode：4765包与4765帧，视频payload、extradata、参数、规范化packet时序一致，解码RGB像素和帧时刻一致。结果在video-copy-check.json。
4. 用真实中文混音与v10音轨检验audio-lag：六窗口均为−171 samples/8kHz，建议补+171点；结果在audio-lag-check.json。细测44.1kHz应另做，而非把8k估计伪装成样点级精度。
5. skill-creator quick_validate通过；本包Markdown内部文件链接已逐项校核；ZIP逐文件SHA256验证结果见压缩包旁的打包校验JSON。

## 范围

实际运行测试在本机Windows与已有Python/NumPy/PyAV环境完成。独立Agent测试是决策/缺口检查，并未生成新人物或执行另一个完整PV。没有跨所有宿主、平台或模型实际运行；任意可读UTF-8的Agent可以读取工作流，自动发现、媒体生成、编码和试听能力由宿主决定。

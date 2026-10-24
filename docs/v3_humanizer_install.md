# humanizer 技能替换记录

> 合成数据 / 已知 DGP。本文件是项目工具配置记录，不是实验结果。

记录日期：2026-10-25。

## 当前结果

**humanizer 3.1.0 已安装到用户全局技能目录，旧 academic-humanizer 入口已禁用并可恢复。** 主会话完成获批操作后，本子任务只读核对安装状态：四个文件与准备目录的 SHA-256 全部一致，旧入口已改名为 `SKILL.md.disabled-v3-20261025`，文件内容与备份一致；全局新目录再次通过官方格式校验。

自动发现按技能安装约定在下一轮生效。本轮需要使用时，可直接读取绝对路径 `C:\Users\26382\.codex\skills\humanizer\SKILL.md`，学术润色同时读取其 `references\academic-integrity.md`。

## 审批审计

第一次由本子任务申请全局安装时，自动审批在命令启动前拒绝，理由是它认为可信请求只有“了解工作目录”，未识别当前目标中的系统级技能替换授权。当时复查确认新目录不存在、旧入口未变，未采用其他方式绕过拒绝。

随后主会话依据当前直接用户授权重新通过 `require_escalated` 审批，完成四文件安装、逐文件哈希校验和旧入口改名，并通知本子任务只读复核。本子任务已复核实际文件状态并重新执行官方校验；没有再次修改全局文件。前一次拒绝保留为审计事件，已经不是当前阻碍。

## 来源与准备产物

| 项目 | 记录 |
|---|---|
| 用户提供的包 | `C:\Users\26382\Downloads\humanizer-main.zip` |
| SHA-256 | `b1210453bc037f534d4d92cfb9b6dce194ac1428a9b11a79392009488b4d6da1` |
| 包内版本 | humanizer 3.1.0，来自 `SKILL.md` 的元数据 |
| 许可证 | MIT，保留 Copyright (c) 2025 Siqi Chen 与许可证全文 |
| 安装准备副本 | `D:\L\practice_project\营销数分项目\out\humanizer_install\staged\humanizer` |
| 已安装全局目录 | `C:\Users\26382\.codex\skills\humanizer` |
| 旧技能目录 | `C:\Users\26382\.codex\skills\academic-humanizer` |
| 旧技能完整备份 | `D:\L\practice_project\营销数分项目\out\humanizer_install\backup\academic-humanizer` |
| 原 ZIP 备份 | `D:\L\practice_project\营销数分项目\out\humanizer_install\backup\humanizer-main.zip` |
| 准备脚本 | `D:\L\practice_project\营销数分项目\out\humanizer_install\prepare_install.py` |
| 文件哈希清单 | `D:\L\practice_project\营销数分项目\out\humanizer_install\manifest.json` |
| 验证记录 | `D:\L\practice_project\营销数分项目\out\humanizer_install\verification.json` |

旧技能备份含 48 个文件，包括原 Git 元数据；备份时每个文件的 SHA-256 与原目录一致。主会话仅将旧技能入口改名禁用，保留了原目录；复核确认禁用入口内容与备份一致。

## 安装内容与适配

全局新目录与准备副本均含以下四个运行时文件：

- `SKILL.md`：保留上游 humanizer 3.1.0 规则，增加学术模式入口和本地适配元数据。
- `LICENSE`：原 MIT 许可证。
- `agents/openai.yaml`：原 Codex 展示信息，保持默认自动选择行为。
- `references/academic-integrity.md`：学术润色的证据与事实保护规则。

未安装压缩包中的未知脚本、插件配置、仓库级 `AGENTS.md`、README 或 CHANGELOG；没有运行任何包内脚本，没有访问网络。归档所有条目通过相对路径、父目录穿越、驱动器标记与符号链接检查。

学术模式要求保留数字、单位、公式、引用键、方法术语、样本分母、适用范围、实质性局限与不确定性；禁止把关联改成因果，把估计改成真值，或把条件结论写成普遍结论。修订事实必须另行核查和显式记录。通用文风规则不能删除研究稿必要结构、合成数据标注、证据溯源或失败条件。新技能用于提高可读性，不用于判断作者身份或规避 AI 使用披露。

## 实际验证

1. 使用项目 `.venv\Scripts\python.exe`，设置 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8` 运行准备脚本，成功。
2. 使用系统 `skill-creator/scripts/quick_validate.py` 校验准备目录，返回 `Skill is valid!`。
3. 用 YAML 解析确认 `name=humanizer`、`description` 为非空字符串；`metadata.version=3.1.0`。
4. 检查 `SKILL.md` 的本地引用 `references/academic-integrity.md`，文件存在。
5. 备份 48 个文件逐一对比 SHA-256，一致；备份 ZIP 与原 ZIP 的 SHA-256 一致。
6. 审批拒绝后复查全局状态：新 `humanizer` 目录不存在，旧 `academic-humanizer/SKILL.md` 仍存在。
7. 主会话获批安装后再次只读核查：全局目录恰含四个文件，逐文件 SHA-256 与准备副本一致；旧 `SKILL.md` 不存在，`SKILL.md.disabled-v3-20261025` 存在且内容与备份一致。
8. 使用 `quick_validate.py` 校验全局目录，再次返回 `Skill is valid!`；全局 YAML 名称、版本、非空描述和本地引用再次通过检查。

这些结果证明全局安装、旧入口禁用与可恢复备份均已完成；不把格式校验当作实际论文润色质量的证明。

## 使用与恢复

下一轮可调用 `$humanizer`；本轮可按上述绝对路径读取使用。学术模式先加载证据保护规则，再应用通用文风规则。原文中的数字、公式、引用与不确定性需逐项核对，不依靠文风技能推断实验结论。

如需恢复旧技能，把 `SKILL.md.disabled-v3-20261025` 改回 `SKILL.md`；若原目录发生其他损坏，可从上述完整备份恢复。恢复时仍须遵守目标路径与审批规则。备份含嵌套 Git 元数据，不应加入本项目版本库。

本子任务仅修改 `docs/v3_humanizer_install.md` 与 `out/humanizer_install/`；全局变更由主会话执行。本子任务未修改项目纲领、验收、进度、交接文件或工程代码。

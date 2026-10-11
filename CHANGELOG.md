## v1.2.1-local.2 — 2026-10-11

- 修复无 CR/LF 的绝对光标重绘使代码保护全程粘滞的问题；水平代码延续保持保护。
- 支持明确的拼接 UI 格式、SGR 字符拆分及同一行最多 16 列的前向空白；保留控制字节、动态尾部与宽度退回。
- 新增启动、帮助、页脚与警告等 16 条提示，词表 65 条、31 组。
- 加入真实录制及 11 项回归：本机 Node 69 项、Python 11 项通过；全部 8 份录制回放有中文，真实官方启动通过。
- 修复 Linux 生命周期测试误用 macOS 临时目录；旧证据归档保持不变并明确报告源码差异。
- 新修订 Linux AMD64 的真实 Docker/CI：69 项 Node、6 项容器内 Python、5 项生命周期及完整模拟交互/安装卸载通过，日志和结果公开。
- 详细核实和验证边界见 ANALYSIS_RESPONSE.md。

## v1.2.1-local.1 — 2026-10-11

- 本地开发版：A～E 共 24 组界面提示、49 条词表记录；按牛津官方在线词义与 CLI 场景修订，未冒称逐条核对第10版英汉原文。
- 仅匹配完整白名单提示，保护明显代码/JSON，保留动态字段；承认正文与 UI 同词时的残余误译。
- 25 ms 有限刷新；短中文标签借用已有空格，否则保留英文，维持显示列数与控制序列。
- 非交互式调用直接使用官方程序，保留 stdout/stderr 与退出状态。
- 独立启动器与归属检查；安装不接管官方入口，卸载不触碰 Codex 配置或用户替换的文件。
- Python 标准库 PTY 取代原生 npm 依赖，支持中文输入、终端缩放和信号。
- 58 项实际测试、完整前端终端测试、官方 0.162.1 帮助/版本透传检查通过。详见 VALIDATION.md。

- 真实 Linux ARM64 隔离容器：58 项 Node、6 项 Python、词表、模拟交互和 shell 安装卸载通过；临时运行环境已删除，所列宿主配置未变。
- 公开脱敏验证材料、精确源码归档、SHA-256 清单、复现工作流与论文式技术报告。

以下保留上游历史记录，仅用于追溯，不描述本版行为。

## 上游 v1.2.0（2026-08-16）

### 变更（定位调整：只做 CLI）

- **不再安装、不再修改 Codex Desktop**：安装脚本删除 localeOverride 写入步骤；桌面版自带官方中文，与本项目无关
- 历史安装若已写入 `[desktop] localeOverride`，uninstall 会自动移除（legacy 清理）
- doctor 移除桌面配置检查，只报告 CLI 状态
- README/AGENTS/CLAUDE 文档同步为「只做 CLI，不碰桌面版」

### 入口

- 终端直接 `codex` = 中文（shadow 接管）
- 会话内 `/chinese`、`/english`、`/language` 切换/帮助
- `--codex-zh-lang zh|en`、`CODEX_ZH_LANG`

## v1.1.2（2026-08-16）

### 修复

- 修复 stdin Buffer 未转字符串导致 /chinese、/english 输入被吞的问题
- 切换提示改为按错误回显里的命令名替换，兼容 Codex 延迟渲染
- /language、/lang 显示语言切换帮助

## v1.1.1（2026-08-16）

### 新增

- **会话内语言切换命令**：在 Codex 输入框输入 `/chinese`（或 `/zh`）回车切中文、`/english`（或 `/en`）切英文；选择写入 settings.json，全局记住
- 包装器新增 `--codex-zh-lang zh|en` 与 `CODEX_ZH_LANG` 环境变量
- doctor 增加「包装器语言设置」检查

### 改进

- 桌面版入口说明：Settings → General → Language → 中文（中国）（安装脚本已自动写入 localeOverride）
- 新增语言切换使用提示

## v1.1.0（2026-08-16）

### 新增

- **codex 命令接管（shadow mode）**：安装后直接输入 `codex` 就是中文，与 claude-code-zh-cn 的使用习惯一致；真实 Codex 入口备份在 shadow-state.json，卸载一键恢复
- 医生增加「codex 命令接管」状态检查

### 改进

- **全译或全不译规则**：多词文本只做完整短语匹配，不再把句子中的单个单词拆出来翻译；修复 `Use /skills` 变成 `Use /技能`、`Codex can read and 编辑 files...` 等混搭问题
- 斜杠命令菜单：选中/未选中的描述都稳定显示中文（补齐全部命令描述词条）
- 模型选择器：补齐全部模型与推理强度描述（Frontier / Strong / Ultra-fast 等）
- 动态模式支持行首符号（⚠、•）前缀，尾随占位符改为贪婪匹配

### 修复

- 删除会把整句拆成中英混合的碎片词条（coding model.、for everyday coding.、信任页散文单词等）
- MCP 启动失败等带前缀的动态警告现在整条翻译

## v1.0.3（2026-08-16）

### 改进

- /model to change 前导空格、Yes,/No, 逗号贴合等信任/启动界面细节
- 去重词条总数 978

## v1.0.2（2026-08-16）

### 新增

- 从 openai/codex rust-v0.147.0 源码候选池中人工筛选并补译 250 条界面词条（认证/登录、用量、审批、插件/MCP、调试等），去重词条总数达到 976
- scripts/verify-release-state.js：package.json / CHANGELOG / tag / GitHub Release 对齐校验

### 改进

- /model 切换与 max 推理强度翻译微调

### 修复

- Windows：优先解析原生 codex.exe 并注入 CODEX_MANAGED_PACKAGE_ROOT，避免 ConPTY 无法直接执行 .cmd shim
- Windows 安装脚本：对非 git 安装目录的更新路径先清理再克隆
- 输出管道 EPIPE 保护（codex-zh --help | head 不再报错）

## v1.0.1（2026-08-16）

### 修复

- install.sh：部分 npm/系统组合下 node-pty 的 spawn-helper 丢失可执行位，安装后显式补齐
- 单元测试改用 `node --test` 自动发现，修复 Windows CI 的 glob 不展开问题
- codexConfigPath 的 CODEX_HOME 断言改为跨平台路径构造
- codex-zh-doctor 现在报告去重后的词条总数

# Changelog

## v1.0.0（2026-08-16）

首个版本：面向 Codex CLI 0.147.0（当前 latest stable）的简体中文本地化扩展。

### 新增

- `codex-zh` PTY 实时翻译包装器：ANSI 安全、宽度守恒、最长匹配、动态模式、语法区保护
- 725 条去重词条：启动/信任、Hook 审核、MCP 状态、模型选择、会话恢复、斜杠命令面板、`--help`、`exec`、doctor 进度等
- 状态动词数据源 `verbs/zh-CN.json` 与中文提示数据源 `tips/zh-CN.json`
- 桌面语言覆盖：`[desktop] localeOverride = "zh-CN"`（只写一个键，自动备份）
- 安装/卸载脚本：`install.sh`、`install.ps1`、`uninstall.sh`、`uninstall.ps1`
- 健康检查命令：`codex-zh-doctor`
- 单元测试（29 项）与数据校验脚本 `validate-data.js`
- 上游候选词提取脚本 `extract-candidates.mjs`（配合 openai/codex 源码使用）

### 改进

- 参照 claude-code-zh-cn 的数据单一来源与术语规范（Hook、MCP、TUI、transcript、Token 保留英文）

### 修复

- 无（首个版本）


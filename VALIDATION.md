# 验证记录

当前修订为 **1.2.1-local.2**：本机 69 项 Node、11 项 Python 与词表（65 条、31 组）检查通过；8 份真实录制回放命中 11～20 次且控制序列未变；新版包装器实际启动官方 CLI，产生 82 个中文字符。新容器/CI 结果独立记录，见 [修复说明](ANALYSIS_RESPONSE.md) 及 [当前验证材料](verification/1.2.1-local.2/README.md)。

以下为 **local.1 的历史容器与本机检查**；保留记录不等于证明旧版实际 TUI 可用，也不作为此次修订的容器结果。

版本：1.2.1-local.1。最终实际容器运行：2026-10-11 约 20:05（Asia/Shanghai）。上游基线为 taekchef/codex-code-zh-cn v1.2.0，提交 d5c554a860ed22483a49c820283439c9eb23746e；文案开发对照官方 Codex CLI 0.162.1。

## 实际通过结果

| 检查 | 结果 | 证据 |
|---|---|---|
| Linux ARM64，Node.js 24.21.0、Python 3.11.2 | 实际执行 | container.log |
| Node | 58 通过、0 失败、0 跳过 | container.log |
| Python 容器/构建检查 | 6 通过 | container.log |
| 词表 | 49 条、24 组通过 | container.log |
| 完整模拟前端 | 中文输入/显示、UTF-8 分块、代码/JSON、编号/按键、退出码 17 通过 | container.log |
| 实际 shell 安装与卸载 | 容器临时目录执行；合成受保护文件哈希未变 | container.log |
| 实际容器隔离 | 禁网、无宿主机挂载、UID/GID 1000、根文件系统只读、能力为 0、NoNewPrivs 为 1 | isolation.json 与 container.log |
| 容器结果 | 退出码 0、没有 OOM | result.json |
| VM 隔离 | 无共享目录、端口转发、SSH agent | vm-isolation.json |
| 清理 | 临时 VM、Docker、容器、镜像、运行程序与下载缓存已删除 | temporary-runtime-result.json |
| 所列宿主路径复查 | 无变化、未恢复覆盖文件 | host-comparison.json |
| 被测源码 | 42 文件；公开源文件与当次归档哈希一致 | context-manifest.json、source-context.tar |

材料位于 [verification/2026-10-11-arm64](verification/2026-10-11-arm64/README.md)。执行 python3 scripts/verify_public_evidence.py 可核对历史公开材料及归档源码身份，并输出当前源码差异；加 --require-current-source 可严格要求一致。它检查内部一致性和已有记录，并不替代独立重跑。

## 本机另行执行的检查

- 58 项 Node 检查和词表、shell/Python 语法检查通过。
- Python 容器工具 6 项与临时运行生命周期 5 项合计 11 项通过；其中只有前 6 项在实际容器中执行。
- 强制启用颜色的 5 项 PTY 检查通过。
- 官方 Codex 0.162.1 帮助/版本透传的 stdout、stderr、退出状态与直接调用逐项相同。
- 本机临时目录安装检查覆盖入口归属、用户替换、拒绝覆盖及特殊字符路径。

这些本机检查是开发记录；公开的 container.log 不包含全部本机原始输出，应与其实际容器计数区分。

## 实际失败与更正

1. Docker legacy builder 无法 COPY 被其排除的 .dockerignore：移除该复制要求，过滤测试改用合成源码。
2. VM 内慢速依赖安装触发 Lima 启动就绪限制：改为 VM 就绪并完成隔离检查后单独安装，分别保存日志。
3. 首次完整容器 Node 检查 56/58 通过，两项 PTY 可见文字被自动 SGR 颜色影响：只对文字断言去除控制序列，保留原始 ANSI 字节断言；最终完整重跑全部通过。

## 范围和限制

交互使用模拟 CLI；容器没有真实 Codex 登录信息，未调用模型完成任务或验证完整真实工具审批。本机前后检查仅覆盖指定配置、认证哈希、官方入口及运行环境路径，不是全磁盘审计。公开结果只保留比较结论，不上传私密备份、认证内容或认证哈希。

终端不能可靠区别 UI 和正文，同一完整提示在正文中独立出现时仍可能误译。代码保护和显示宽度是启发式；短标签空间不足时保留英文。测试通过不保证全部版本和终端兼容，也没有测量误译概率或用户效率。

词典依据为牛津官方公开英文释义与 CLI 场景适配；未直接取得第10版完整英汉条目。[论文报告](paper/PAPER.zh-CN.md) 进一步说明方法、证据和有效性边界。

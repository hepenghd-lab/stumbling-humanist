# 1.2.1-local.2 修订验证

本目录与旧版 2026-10-11-arm64 容器目录分开。旧目录保持原字节；本目录记录报告问题修复后的源码、回放和真实官方启动。

| 文件 | 内容 |
|---|---|
| recording-provenance.json | 用户提供证据包身份、36 文件哈希核对、原始及公开录制哈希 |
| recordings/*.ansi | 8 份完整脱敏录制；保留 ANSI 控制序列与等宽布局 |
| before-replay.json / after-replay.json | 固定旧源码与修订源码对相同公开输入的回放结果 |
| local-node.log | 本机 69 项 Node 检查输出 |
| live-wrapper-startup.ansi / .json | 新包装器实际驱动官方 CLI 启动；使用临时设置、本地无效模型地址和合成密钥 |
| mock-frontend.json | 模拟 CLI 交互检查；不是实际模型任务 |
| context-manifest.json / source-context.tar | 此次 47 个受限容器构建源文件的身份与快照 |
| SHA256SUMS | 本目录公开文件的 SHA-256 |

会话 UUID、临时工作目录和额度百分比已脱敏；不存在真实凭证或私密配置。回放报告只含计数、文件哈希和保留检查，不公开分析者的完整脚本或完整分析报告。raw 中的早期未提交输入录制不能计为成功模型任务。

复现修订后的回放：

```sh
node scripts/replay_recordings.js verification/1.2.1-local.2/recordings
node --test
python3 -m unittest discover -s scripts -p 'test_*.py'
```

复现旧版对照时，可把 [旧源码归档](../2026-10-11-arm64/source-context.tar) 解到独立临时目录，再将该目录作为 replay_recordings.js 的第二个路径参数。无需网络、账户或修改全局入口。

详细问题对应、计数解释及边界见 [ANALYSIS_RESPONSE.md](../../ANALYSIS_RESPONSE.md)。文件哈希及回放属于可重算材料，不是安全证明或同行评审。

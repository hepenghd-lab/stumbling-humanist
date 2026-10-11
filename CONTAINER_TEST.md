# 隔离容器测试

当前修订 local.2 的源清单为 47 个文件（新增重绘测试、帮助器和录制样例）。下述 58/6 容器结果属于旧版 local.1；新修订的实际结果单独保存，不能沿用历史通过状态。

2026-10-11 已完成真实 Linux ARM64 容器测试：58 项 Node 检查、6 项 Python 检查、49 条词表验证、完整模拟 Codex 中文交互及实际 shell 安装/卸载全部通过。最终记录见 [VALIDATION.md](VALIDATION.md)。临时运行环境已清理，所检查的宿主机配置、认证文件哈希和官方 Codex 入口未变。

## 在 macOS ARM64 上重复测试

从项目根目录在普通终端执行：

```sh
bash run-container-test.command
```

本次验证已完成；以下用于独立复现。每次运行会重新备份所列配置，并在结束时比较哈希；不会自动覆盖运行期间用户修改的配置。认证文件只记录哈希，不复制到备份、构建上下文或容器。

运行流程使用单独的临时目录和 LIMA_HOME，下载并校验固定版本的 Lima 2.2.1 与 Ubuntu 24.04 ARM64 镜像。无需宿主机 sudo、Homebrew 安装或更改现有 Docker context。VM 分配 2 CPU、2 GiB 内存、12 GiB 稀疏磁盘；建议至少留出 8 GiB 可用空间。镜像、软件包和构建基础镜像下载需要联网。

来源与 SHA-256：

- [Lima v2.2.1](https://github.com/lima-vm/lima/releases/tag/v2.2.1)：Darwin ARM64 发布包，`9e9eacce88f37e185c346bad73aa6136f738d8cdf8c3bb23cd42b071824bc66e`。
- [Lima 官方 Ubuntu 24.04 镜像配置](https://github.com/lima-vm/lima/blob/v2.2.1/templates/_images/ubuntu-24.04.yaml)：Ubuntu release-20260926 ARM64 镜像，`1d6bffe64b848468ac97f821d369a4846d983de1800ccf6b5ec8853e85cefc55`。

VM 使用 VZ、plain 模式，无宿主目录挂载、端口转发、SSH agent 或 X11 转发，不读取现有 SSH 公钥。先完成 VM 就绪和隔离检查，再在 VM 内安装 Docker/Python，安装阶段最长 30 分钟。跳过可选 APT 索引而保留软件包签名检查。

结束或正常错误时，只停止/删除本次 VM，校验所有权标记后删除临时目录，并复查宿主机所列路径。不会全局 prune，也不会删除其他 VM、镜像或容器。SIGKILL 或断电无法执行正常清理，应按保留的运行记录检查本次目录。

## 使用已有 Docker

如果已经有可信的 Docker 服务，也可使用 Python 3.9+：

```sh
python3 scripts/container_test.py
```

`--prepare` 只生成构建上下文和清单；`--offline` 需要已缓存基础镜像及相应依赖。查看 `--help` 可指定已有引擎。脚本不会切换全局 Docker context；已有服务模式结束后会保留测试镜像及构建缓存，可按记录中的具体镜像 ID 单独清理。

当前构建上下文严格限定为 47 个必要源码文件，拒绝文件或父目录符号链接，归零归档所有权和时间字段，不发送主目录、认证、配置、测试日志、私密备份或整个工作区。构建阶段只安装基础运行依赖，之后才复制项目代码；项目测试在受限容器中执行。基础镜像标签可能发生变化，结果记录具体被测 image ID，不能据此保证未来重新构建字节完全一致。

## 实际验证的限制

最终容器检查了 Docker 配置及运行时状态：

- 无宿主机挂载、无端口映射，网络关闭，只有回环接口。
- UID/GID 1000，根文件系统只读；临时写入仅在 256 MiB tmpfs。
- capabilities 全部删除，启用 no-new-privileges。
- 2 CPU、512 MiB 内存、256 个进程；清空代理环境变量。

容器中执行 58 项 Node 检查和 6 项 Python 检查，词表、语法、完整 PTY 交互及 shell 安装/卸载检查。安装测试仅使用容器临时目录、合成官方 CLI、配置和认证文件，不使用真实账户。本机另通过 5 项临时运行环境生命周期检查，与上述 6 项合计 11 项 Python 检查；不能将 11 项全部说成容器内运行。

范围包括中文输入、UTF-8 分块、ANSI 保留、终端尺寸、信号/退出码、代码和 JSON 保留、入口所有权、卸载边界。尚未验证真实模型任务或完整工具审批。包装器从终端字节流识别提示，正文恰好等于白名单提示仍可能被误译，空间不足时可能保留英文。

Docker 机制参见官方的 [运行参数](https://docs.docker.com/engine/containers/run/)、[构建上下文](https://docs.docker.com/build/concepts/context/) 和 [tmpfs](https://docs.docker.com/engine/storage/tmpfs/) 文档。

## 日志与本次修正

`test-results/container/` 保留启动、VM 内安装、构建和容器完整输出，以及源码哈希清单、隔离检查、结果 JSON。私密备份位于 `test-results/host-safety/`，目录权限 0700、备份文件 0600。源码压缩包排除整个 test-results。前后比较只覆盖记录中的路径，不代表全磁盘审计。

开发中修正了三项实际问题：

1. Docker legacy builder 将 `.dockerignore` 排除出可复制上下文；Dockerfile 不再 COPY 此文件，过滤测试改用合成文件。
2. 将慢速 Docker 安装移出启动 provision，避开 Lima 内部 [200 次、每次 3 秒的就绪检查](https://github.com/lima-vm/lima/blob/v2.2.1/pkg/hostagent/requirements.go)；启动与安装分别记录日志。
3. 两项 PTY 可见文字断言先去除终端自动颜色，避免正确的布尔/尺寸输出误报失败；专门的 ANSI 字节保留断言仍检查原始输出。

最终 `temporary-runtime-result.json` 中测试通过、运行环境已删除、所列设置未变均为 true，且错误列表为空。

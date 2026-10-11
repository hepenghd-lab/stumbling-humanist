#!/usr/bin/env node
'use strict';

/**
 * codex-zh — run OpenAI Codex CLI with live Simplified-Chinese output.
 *
 * Spawns the official `codex` inside a POSIX pseudo-terminal and translates
 * approved complete UI fragments. Non-interactive calls bypass the wrapper.
 * Terminal escape sequences
 * pass through untouched; each replacement is padded to the original display
 * width so layouts, box borders and cursor positions stay aligned.
 *
 * Usage:  codex-zh [codex args...]
 *
 * codex-zh specific flags (consumed before Codex sees them):
 *   --codex-bin <path>          use an explicit Codex executable
 *   --codex-zh-no-translate     passthrough without translation
 *   --codex-zh-help             show this help
 *
 * Environment:
 *   CODEX_ZH_DISABLE=1          same as --codex-zh-no-translate
 *   CODEX_ZH_SKIP=1             internal guard against recursive wrapping
 */

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const { StringDecoder } = require('string_decoder');
const { StreamTranslator } = require('../lib/translator');
const { shouldWrap } = require('../lib/run-mode');
const detect = require('../lib/detect');
const settings = require('../lib/settings');
const { createToggleDetector } = require('../lib/language-toggle');

const HELP = `codex-zh-local — Codex CLI 固定界面提示中文包装器

Usage:
  codex-zh-local [--codex-bin <path>] [--codex-zh-lang zh|en] [codex args...]

仅在交互界面中翻译已确认的 A～E 提示；exec、管道、帮助等直接使用官方程序。
词表外的文字保留原文；普通文本独立出现同一提示时仍可能误译。
   --codex-bin <path>          指定 Codex 可执行文件
   --codex-zh-lang zh|en       本次启动语言（默认读取 settings.json）
   --codex-zh-no-translate     禁用翻译（等于 CODEX_ZH_DISABLE=1）
   --codex-zh-help             显示本帮助

会话内切换（在 Codex 输入框里直接输入）：
   /chinese 或 /zh              切换为中文（并全局记住）
   /english 或 /en              切换为英文（并全局记住）

Examples:
   codex-zh-local
   codex-zh-local exec "列出当前目录" --sandbox read-only
   codex-zh-local --help | less
`;

function fail(msg, code = 1) {
  process.stderr.write(`codex-zh: ${msg}\n`);
  process.exit(code);
}

function parseArgs(argv) {
  const opts = {
    translate: process.env.CODEX_ZH_DISABLE !== '1',
    codexBin: null,
    language: process.env.CODEX_ZH_LANG || null,
  };
  const rest = [];
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--') {
      rest.push(...argv.slice(i));
      break;
    }
    if (arg === '--codex-zh-help' || arg === '-zh-help') {
      opts.help = true;
    } else if (arg === '--codex-zh-no-translate' || arg === '--no-translate') {
      opts.translate = false;
    } else if (arg === '--codex-zh-lang') {
      i += 1;
      opts.language = argv[i];
      if (!opts.language) fail('--codex-zh-lang requires zh or en');
    } else if (arg.startsWith('--codex-zh-lang=')) {
      opts.language = arg.slice('--codex-zh-lang='.length);
    } else if (arg === '--codex-bin') {
      i += 1;
      opts.codexBin = argv[i];
      if (!opts.codexBin) fail('--codex-bin requires a path');
    } else if (arg.startsWith('--codex-bin=')) {
      opts.codexBin = arg.slice('--codex-bin='.length);
    } else {
      rest.push(arg);
    }
  }
  if (opts.language === 'zh') opts.language = 'zh-CN';
  if (opts.language && !['zh-CN', 'en'].includes(opts.language)) {
    fail('--codex-zh-lang only accepts zh, zh-CN or en');
  }
  return { opts, rest };
}

function loadEntries() {
  const candidates = [
    path.join(__dirname, '..', 'data', 'ui-translations-local.json'),
  ];
  const entries = [];
  for (const file of candidates) {
    if (!fs.existsSync(file)) continue;
    try {
      const data = JSON.parse(fs.readFileSync(file, 'utf8'));
      for (const entry of Array.isArray(data) ? data : []) {
        if (entry && typeof entry.en === 'string' && typeof entry.zh === 'string') {
          entries.push(entry);
        }
      }
    } catch (err) {
      process.stderr.write(`codex-zh: 无法读取翻译数据 ${file}: ${err.message}\n`);
    }
  }
  return entries;
}

async function main() {
  const { opts, rest } = parseArgs(process.argv.slice(2));
  if (opts.help) {
    process.stdout.write(HELP);
    return;
  }

  let codexBin = detect.resolveCodexBin(opts.codexBin);
  if (!codexBin) {
    fail(
      '未找到 Codex CLI。请先安装：npm install -g @openai/codex@latest，' +
        '或用 --codex-bin 指定可执行文件路径。'
    );
  }

  // Windows 上 npm 的 codex 入口是 .cmd shim，ConPTY 直接执行会失败；
  // 优先解析到原生 codex.exe，并补上 launcher 注入的包根环境变量。
  const managedRootEnv = {};
  if (process.platform === 'win32') {
    const native = detect.resolveNativeBinary(codexBin);
    if (native) {
      const platformPkgRoot = path.resolve(native, '..', '..', '..');
      const atOpenai = path.dirname(platformPkgRoot);
      const codexPkgRoot = path.join(atOpenai, 'codex');
      if (fs.existsSync(codexPkgRoot)) {
        managedRootEnv.CODEX_MANAGED_PACKAGE_ROOT = codexPkgRoot;
      }
      codexBin = native;
    }
  }

  // 内部守卫：shim 的孙子进程不再二次包装。
  if (process.env.CODEX_ZH_SKIP === '1') {
    const child = spawnSync(codexBin, rest, { stdio: 'inherit', env: process.env });
    process.exit(child.status == null ? 1 : child.status);
  }

  if (!opts.translate || !shouldWrap(rest, process.stdin.isTTY, process.stdout.isTTY)) {
    const child = spawnSync(codexBin, rest, { stdio: 'inherit', env: process.env });
    if (child.error) fail(child.error.message);
    const signals = { SIGHUP: 1, SIGINT: 2, SIGTERM: 15, SIGKILL: 9 };
    process.exit(child.signal ? 128 + (signals[child.signal] || 1) : (child.status ?? 1));
  }

  const pty = require('../lib/pty-bridge');

  // 语言状态：优先本次启动参数/环境变量，其次持久化设置（/chinese 会写它）。
  let language = opts.language;
  if (!language || (language !== 'zh-CN' && language !== 'en')) {
    language = settings.currentLanguage();
  }
  if (language !== 'zh-CN' && language !== 'en') language = 'zh-CN';
  if (!opts.translate) language = 'en';

  const parent = {
    cols: process.stdout.isTTY ? process.stdout.columns : 120,
    rows: process.stdout.isTTY ? process.stdout.rows : 36,
  };
  const term = process.env.TERM && process.env.TERM !== 'dumb'
    ? process.env.TERM
    : 'xterm-256color';

  const childEnv = {
    ...process.env,
    ...managedRootEnv,
    TERM: term,
    CODEX_ZH_SKIP: '1',
    CODEX_ZH_WRAPPED: '1',
  };

  process.stdout.on('error', () => {}); // swallow EPIPE when piped into head/less
  const entries = loadEntries();
  const pendingCommands = [];

  // /chinese、/english 切换：Codex 会报 Unrecognized command，我们把这类
  // 错误消息替换成切换成功的提示（按错误里的命令名决定中/英文提示）。
  const applyLanguage = (lang, typedCommand) => {
    pendingCommands.push(typedCommand.toLowerCase());
    if (lang === null) return; // /language、/lang 只显示帮助，不切换
    language = lang;
    settings.setLanguage(language);
    translator.enabled = language === 'zh-CN';
  };

  const translator = new StreamTranslator(entries, (chunk) => {
    process.stdout.write(chunk);
  }, {
    enabled: language === 'zh-CN',
    onBeforeText: (text) => {
      const m = /Unrecognized command '\/(chinese|zh|english|en|language|lang)'/i.exec(text);
      if (m) {
        const cmd = m[1].toLowerCase();
        const pending = pendingCommands.indexOf(cmd);
        if (pending === -1) return undefined;
        pendingCommands.splice(pending, 1);
        if (cmd === 'language' || cmd === 'lang') {
          return language === 'zh-CN'
            ? '语言切换：输入 /chinese 切中文，/english 切英文（全局生效）。'
            : 'Language: type /chinese for Chinese or /english for English (persisted).';
        }
        const lang = cmd === 'chinese' || cmd === 'zh' ? 'zh-CN' : 'en';
        return lang === 'zh-CN'
          ? '✅ 已确认的界面提示中文模式已开启。'
          : '✅ English mode enabled.';
      }
      return undefined;
    },
  });

  // stdin 行缓冲：识别 /chinese、/zh、/english、/en + Enter。
  const toggleDetector = createToggleDetector(applyLanguage);
  const decoder = new StringDecoder('utf8');

  let p;
  try {
    p = pty.spawn(codexBin, rest, {
      name: term,
      cols: parent.cols,
      rows: parent.rows,
      cwd: process.cwd(),
      env: childEnv,
    });
  } catch (err) {
    fail(`无法启动 Codex（${codexBin}）：${err.message}`);
  }

  p.onData((data) => translator.feed(data));
  p.onError((message) => process.stderr.write(`codex-zh-local: ${message}\n`));

  // stdin → child PTY.
  if (process.stdin.isTTY) {
    try {
      process.stdin.setRawMode(true);
    } catch {}
  }
  process.stdin.on('data', (data) => {
    try {
      const text = Buffer.isBuffer(data) ? decoder.write(data) : String(data);
      toggleDetector(text);
      p.write(text);
    } catch {}
  });
  process.stdin.on('end', () => {
    const tail = decoder.end();
    if (tail) p.write(tail);
    p.endInput();
  });
  process.stdin.resume();

  // Terminal resize.
  process.stdout.on('resize', () => {
    try {
      if (process.stdout.columns && process.stdout.rows) {
        p.resize(process.stdout.columns, process.stdout.rows);
      }
    } catch {}
  });
  process.on('SIGWINCH', () => {
    try {
      if (process.stdout.columns && process.stdout.rows) {
        p.resize(process.stdout.columns, process.stdout.rows);
      }
    } catch {}
  });

  // Forward signals.
  const forwardSignal = (signal) => {
    try {
      p.kill(signal);
    } catch {}
  };
  process.on('SIGINT', () => forwardSignal('SIGINT'));
  process.on('SIGTERM', () => forwardSignal('SIGTERM'));
  process.on('SIGHUP', () => forwardSignal('SIGHUP'));

  const finish = (code, signal) => {
    translator.end();
    try {
      if (process.stdin.isTTY) process.stdin.setRawMode(false);
    } catch {}
    if (signal) {
      const signum = typeof signal === 'number' ? signal : ({ SIGHUP: 1, SIGINT: 2, SIGTERM: 15, SIGKILL: 9 }[signal] || 1);
      process.exit(128 + signum);
    } else {
      process.exit(code == null ? 0 : code);
    }
  };

  p.onExit(({ exitCode, signal }) => finish(exitCode, signal));
}

main().catch((err) => fail(err && err.stack ? err.stack : String(err)));


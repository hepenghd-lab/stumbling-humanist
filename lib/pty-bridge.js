'use strict';

const { spawn: spawnProcess } = require('child_process');
const { StringDecoder } = require('string_decoder');
const path = require('path');

/** POSIX PTY transport using Python's standard library; no native npm addon. */
function spawn(bin, args, opts) {
  if (process.platform === 'win32') throw new Error('本地修订版的交互包装器支持 macOS/Linux。');
  const python = process.env.CODEX_ZH_PYTHON || 'python3';
  const child = spawnProcess(python, ['-u', path.join(__dirname, '..', 'scripts', 'pty_bridge.py'), bin, ...args], {
    cwd: opts.cwd,
    env: { ...opts.env, CODEX_ZH_COLS: String(opts.cols), CODEX_ZH_ROWS: String(opts.rows) },
    stdio: ['pipe', 'pipe', 'pipe', 'pipe'],
  });
  const dataHandlers = [];
  const exitHandlers = [];
  const errorHandlers = [];
  const decoder = new StringDecoder('utf8');
  let controlText = '';
  let status = null;
  let errors = '';
  let finished = false;
  const reportError = (error) => {
    for (const fn of errorHandlers) fn(error.message || String(error));
  };
  const send = (message) => {
    if (!finished && child.stdio[3] && !child.stdio[3].destroyed) {
      child.stdio[3].write(JSON.stringify(message) + '\n');
    }
  };
  child.stdout.on('data', (bytes) => {
    const text = decoder.write(bytes);
    if (text) for (const fn of dataHandlers) fn(text);
  });
  child.stdout.on('end', () => {
    const tail = decoder.end();
    if (tail) for (const fn of dataHandlers) fn(tail);
  });
  child.stderr.on('data', (bytes) => { errors = (errors + bytes.toString()).slice(-4096); });
  if (child.stdio[3]) child.stdio[3].on('data', (bytes) => {
    controlText += bytes.toString('utf8');
    let newline;
    while ((newline = controlText.indexOf('\n')) !== -1) {
      const line = controlText.slice(0, newline);
      controlText = controlText.slice(newline + 1);
      try {
        const message = JSON.parse(line);
        if (message.event === 'exit') status = message;
        if (message.event === 'error') reportError(message.message);
      } catch { reportError('PTY 控制消息无效'); }
    }
  });
  for (const stream of [child.stdin, child.stdio[3]]) {
    if (stream) stream.on('error', (error) => {
      if (!['EPIPE', 'ECONNRESET'].includes(error.code)) reportError(error);
    });
  }
  child.on('error', reportError);
  child.on('close', (code, signal) => {
    finished = true;
    if (errors) reportError(errors.trim());
    const signals = { SIGHUP: 1, SIGINT: 2, SIGTERM: 15, SIGKILL: 9 };
    const result = status || { exitCode: code ?? 1, signal: signal ? signals[signal] || 1 : 0 };
    for (const fn of exitHandlers) fn(result);
  });
  return {
    onData(fn) { dataHandlers.push(fn); },
    onExit(fn) { exitHandlers.push(fn); },
    onError(fn) { errorHandlers.push(fn); },
    write(text) { if (!finished) child.stdin.write(text); },
    endInput() { if (!finished) child.stdin.end(); },
    resize(cols, rows) { send({ op: 'resize', cols, rows }); },
    kill(signal) { send({ op: 'signal', signal }); },
  };
}

module.exports = { spawn };

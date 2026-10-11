'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const entries = require('../data/ui-translations-local.json');
const { StreamTranslator } = require('../lib/translator');
const { stringWidth } = require('../lib/width');
const clean = (text) => text.replace(/\x1b\[[0-9;:]*m/g, '');
function run(chunks, opts = {}) {
  let out = '';
  const stream = new StreamTranslator(entries, chunk => { out += chunk; }, { flushIntervalMs: 0, ...opts });
  chunks.forEach(chunk => stream.feed(chunk));
  stream.end();
  return out;
}

test('approved status meanings are translated without changing display columns', () => {
  const output = run(['\x1b[1mExplored\x1b[0m\nFailed\n']);
  assert.equal(output, '\x1b[1m已探查  \x1b[0m\n失败  \n');
  assert.equal(stringWidth(clean(output)), stringWidth('Explored\nFailed\n'));
});
test('short Run/Ran labels borrow only existing padding across styling', () => {
  assert.equal(run(['\x1b[1mRun\x1b[0m python\n']), '\x1b[1m运行\x1b[0mpython\n');
  assert.equal(run(['Ran  ', '\x1b[0m', 'cargo test\n']), '运行 \x1b[0mcargo test\n');
  assert.equal(run(['You ran', '\x1b[0m', ' cargo\n']), '你运行了\x1b[0mcargo\n');
});
test('insufficient padding and cursor movement retain original text and controls', () => {
  assert.equal(run(['Run']), 'Run');
  assert.equal(run(['Ran', '\x1b[3;5H', 'x']), 'Ran\x1b[3;5Hx');
});
test('all approved A–E elements are represented, including omitted variants', () => {
  const required = ['Exploring','Explored','Run','Running','Ran','You ran','Read','List','Search','Calling','Called','Searching for','Searched for','Searching page','Searched page','Working','failed','${count} failed','Failed (exit ${code})','(no output)','Failed to apply patch','Error: ${detail}','Background output','connected','starting','authentication required','not started','disabled','cancelled','unknown','Loading MCP inventory','Would you like to run the following command?','Yes, just this once','Yes, proceed','No, and tell Codex what to do differently','to confirm','to cancel','to interrupt','${percent}% context left','for shortcuts','to queue message','again to quit','to edit previous message'];
  const actual = new Set(entries.map(entry => entry.en));
  required.forEach(word => assert.ok(actual.has(word), 'Missing: ' + word));
});
test('dynamic counts, exit codes, percent and error details remain exact', () => {
  assert.equal(run(['• 12 failed\n']).trim(), '• 12 项失败');
  assert.equal(run(['Failed (exit -17)\n']).trim(), '失败（退出码-17）');
  assert.equal(run(['Error: /tmp/a b.py: ${Working}\n']).trim(), '错误：/tmp/a b.py: ${Working}');
  assert.equal(run(['37% context left\n']).trim(), '剩余上下文 37%');
  assert.equal(run(['  └ (no output)\n']).trim(), '└ （无输出）');
});
test('obvious code, JSON, commands and paths are never translated', () => {
  const inputs = ['print("Working")\n','{"status":"Working"}\n','const label = "Failed";\n','/tmp/Failed\n','--model\n','/model\n','run python script.py\n','The operation Failed yesterday.\n'];
  for (const input of inputs) assert.equal(run([input]), input);
});
test('code protection survives ANSI style boundaries', () => {
  const input = 'print("\x1b[1mWorking\x1b[0m")\n';
  assert.equal(run([input]), input);
});
test('fenced code stays untouched and following UI labels can translate', () => {
  assert.equal(run(['```python\nWorking\n```\nFailed\n']), '```python\nWorking\n```\n失败  \n');
});
test('a phrase spanning chunks can translate, but arbitrary substring matches cannot', () => {
  assert.equal(run(['Searching ', 'for\n']).trim(), '正在搜索');
  assert.equal(run(['Text: Searching for bugs\n']), 'Text: Searching for bugs\n');
});
test('plain prompts and short labels flush on the first bounded timer', () => {
  let out = '', callback, delay;
  const stream = new StreamTranslator(entries, x => { out += x; }, {
    schedule: (fn, ms) => { callback = fn; delay = ms; return 1; }, cancel: () => {},
  });
  stream.feed('Password: ');
  assert.equal(out, '');
  assert.equal(delay, 25);
  callback();
  assert.equal(out, 'Password: ');
  stream.feed('Run');
  callback();
  assert.equal(out, 'Password: Run');
  stream.end();
});
test('a real timer releases a newline-free prompt before stream end', async () => {
  let out = '';
  const stream = new StreamTranslator(entries, x => { out += x; });
  stream.feed('Password: ');
  await new Promise(resolve => setTimeout(resolve, 80));
  assert.equal(out, 'Password: ');
  stream.end();
});
test('continuous large output is bounded and unchanged', () => {
  let out = '';
  const stream = new StreamTranslator(entries, x => { out += x; }, { flushIntervalMs: 0 });
  const text = 'x'.repeat(70000);
  stream.feed(text);
  assert.equal(out, text);
  assert.equal(stream.tokenizer.pending.length, 0);
  stream.end();
});
test('disabled translation and end are byte preserving and idempotent', () => {
  assert.equal(run(['Working\n'], { enabled: false }), 'Working\n');
  let out = '';
  const stream = new StreamTranslator(entries, x => { out += x; }, { flushIntervalMs: 0 });
  stream.feed('Failed'); stream.end(); stream.end(); stream.feed('Working');
  assert.equal(out, '失败  ');
});
test('ordinary standalone allowlisted words remain an explicit residual ambiguity', () => {
  assert.equal(run(['Working']), '工作中 ');
});
test('numbered approval rows retain their option number and keyboard key', () => {
  assert.equal(run(['› 1. Yes, proceed (y)\n']).trim(), '› 1. 是，继续 (y)');
});
test('ellipsis and compact footer variants remain translatable', () => {
  assert.equal(run(['Loading MCP inventory...\n']).trim(), '正在加载 MCP 清单...');
  assert.equal(run(['to queue\n']).trim(), '排队');
  assert.equal(run(['again to edit previous message\n']).trim(), '再按一次编辑上一条消息');
});
test('switching to English does not translate an already buffered short label', () => {
  let out = '';
  const stream = new StreamTranslator(entries, x => { out += x; }, { flushIntervalMs: 0 });
  stream.feed('Run\x1b[0m');
  stream.enabled = false;
  stream.feed(' python\n');
  stream.end();
  assert.equal(out, 'Run\x1b[0m python\n');
});

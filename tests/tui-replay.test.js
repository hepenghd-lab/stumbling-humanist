'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const entries = require('../data/ui-translations-local.json');
const { StreamTranslator } = require('../lib/translator');
const { AnsiTokenizer } = require('../lib/ansi-tokenizer');
const { stringWidth } = require('../lib/width');
const { screen } = require('./helpers-screen');
function replay(input, split = 4096) {
  let output = '';
  const translator = new StreamTranslator(entries, text => { output += text; }, { flushIntervalMs: 0 });
  for (let n = 0; n < input.length; n += split) translator.feed(input.slice(n, n + split));
  translator.end();
  return { output, stats: translator.stats };
}
function segments(input) {
  let texts = [], controls = [];
  const tokenizer = new AnsiTokenizer({ onText: x => texts.push(x), onRaw: x => controls.push(x) });
  tokenizer.feed(input); tokenizer.end();
  return { texts, controls };
}
const plain = input => segments(input).texts.join('');
test('absolute-position repaint recovers after version and code rows without LF', () => {
  const input = '\x1b[1;1H>_ OpenAI Codex (v0.162.1)\x1b[2;1Hprint("Working")\x1b[38;3H• Working (2s • esc to interrupt)';
  const { output } = replay(input);
  assert.ok(plain(output).includes('工作中'));
  assert.ok(plain(output).includes('中断'));
  assert.ok(output.includes('print("Working")'));
  assert.deepEqual(segments(output).controls, segments(input).controls);
});
test('composed action row translates only label, retaining command bytes and separation', () => {
  const command = 'echo "Working"; printf "%s" /tmp/Failed';
  const input = '\x1b[5;1H• Ran ' + command;
  const { output } = replay(input, 1);
  // One original prefix space supplies the extra Chinese display cell.
  assert.ok(plain(output).startsWith('•运行 '));
  assert.ok(output.endsWith(command));
  assert.equal(stringWidth(plain(output)), stringWidth(plain(input)));
});
test('same-row horizontal cursor movement does not unlock styled code', () => {
  const input = '\x1b[4;1Hprint("\x1b[10G\x1b[1mWorking\x1b[0m")';
  assert.equal(replay(input).output, input);
});
test('backward CUP within a code row also retains protection', () => {
  const input = '\x1b[4;1Hprint("abc")\x1b[4;8H\x1b[1mWorking\x1b[0m';
  assert.equal(replay(input).output, input);
});
test('SGR per-character shimmer can match a whole UI label', () => {
  const input = '\x1b[8;1H• ' + [...'Working'].map((c,i) => '\x1b[38;5;' + (200+i) + 'm' + c).join('') + '\x1b[0m (1m 02s • esc to interrupt)';
  const { output } = replay(input, 1);
  assert.ok(plain(output).includes('工作中'));
  assert.ok(plain(output).includes('1m 02s'));
  assert.deepEqual(segments(output).controls, segments(input).controls);
  assert.equal(stringWidth(plain(output)), stringWidth(plain(input)));
});
test('known multi-hint footer is matched as a UI structure', () => {
  const input = '\x1b[30;1H← for agents · ? for shortcuts';
  const { output } = replay(input);
  assert.ok(plain(output).includes('查看代理'));
  assert.ok(plain(output).includes('查看快捷键'));
  assert.ok(plain(output).includes('←'));
  assert.ok(plain(output).includes('?'));
  assert.equal(stringWidth(plain(output)), stringWidth(plain(input)));
});
test('prose and JSON mentioning composed labels are not substring-translated', () => {
  for (const input of ['The screen says Working (2s • esc to interrupt)', '{"status":"• Ran echo hi"}', 'print("• Working")']) {
    assert.equal(replay(input).output, input);
  }
});
test('real official CLI startup capture translates beyond the version row', () => {
  const input = fs.readFileSync(path.join(__dirname, 'fixtures/codex-0.162.1-startup.ansi'), 'utf8');
  const { output, stats } = replay(input, 1);
  assert.ok(stats.hits > 0);
  assert.ok(plain(output).includes('让 Codex'));
  assert.ok(plain(output).includes('查看快捷键'));
  assert.deepEqual(segments(output).controls, segments(input).controls);
});
test('analyst real task recording retains commands and keys in rendered cells', () => {
  const input = fs.readFileSync(path.join(__dirname, 'fixtures/codex-0.162.1-task.ansi'), 'utf8');
  const { output, stats } = replay(input, 1);
  const rendered = screen(output);
  const result = rendered.concat(rendered.history).join('\n');
  assert.ok(stats.hits >= 5);
  for (const word of ['工作中','中断','运行','echo hi','查看快捷键','查看代理','耗时']) {
    assert.ok(result.includes(word), word);
  }
  assert.deepEqual(segments(output).controls, segments(input).controls);
  assert.ok(screen(output)[20].endsWith('echo hi'));
  assert.ok(result.includes('esc'));
  assert.ok(result.includes('22:58'));
});
test('wide glyph crossing a cursor boundary retains the original fragment', () => {
  const input = '\x1b[3;1HA\x1b[3;2Hsk Codex to do anything';
  const { output } = replay(input);
  assert.deepEqual(segments(output).controls, segments(input).controls);
  assert.equal(screen(output)[2], screen(input)[2]);
});
test('timer flush followed by another row does not retain code protection', () => {
  let output = '', flush;
  const stream = new StreamTranslator(entries, x => output += x, {
    schedule: fn => { flush = fn; return 1; }, cancel: () => {}
  });
  stream.feed('\x1b[2;1H>_ OpenAI Codex (v0.162.1)');
  flush();
  stream.feed('\x1b[3;1HWorking');
  flush(); stream.end();
  assert.ok(plain(output).includes('工作中'));
});

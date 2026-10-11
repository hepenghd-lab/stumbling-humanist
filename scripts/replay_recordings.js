#!/usr/bin/env node
'use strict';
// Offline comparison only: no Codex execution, network, credentials or source patches.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { StringDecoder } = require('node:string_decoder');
const root = path.resolve(process.argv[3] || path.join(__dirname,'..'));
const directory = path.resolve(process.argv[2] || path.join(__dirname,'../tests/fixtures'));
const { StreamTranslator } = require(path.join(root,'lib/translator'));
const { AnsiTokenizer } = require(path.join(root,'lib/ansi-tokenizer'));
const entries = JSON.parse(fs.readFileSync(path.join(root,'data/ui-translations-local.json'),'utf8'));
function controls(text) {
  const raw = [];
  const parser = new AnsiTokenizer({ onText: () => {}, onRaw: x => raw.push(x) });
  parser.feed(text); parser.end(); return raw;
}
const reports = [];
for (const name of fs.readdirSync(directory).filter(x => /\.(bin|ansi)$/.test(x)).sort()) {
  const input = fs.readFileSync(path.join(directory,name));
  let output = '';
  const stream = new StreamTranslator(entries, x => output += x, { flushIntervalMs: 0 });
  const decoder = new StringDecoder('utf8');
  for (let n=0;n<input.length;n+=997) stream.feed(decoder.write(input.subarray(n,n+997)));
  stream.feed(decoder.end()); stream.end();
  reports.push({
    file: name, input_sha256: crypto.createHash('sha256').update(input).digest('hex'),
    input_bytes: input.length, output_bytes: Buffer.byteLength(output), hits: stream.stats.hits,
    cjk_characters: (output.match(/[\u4e00-\u9fff]/g)||[]).length,
    width_fallbacks: stream.stats.widthFallbacks,
    controls_unchanged: JSON.stringify(controls(input.toString('utf8'))) === JSON.stringify(controls(output)),
    byte_identical: input.equals(Buffer.from(output)),
    invalid_utf8_output: output.includes('\ufffd')
  });
}
console.log(JSON.stringify({ offline_replay: true, records: reports },null,2));
if (reports.some(r=>!r.controls_unchanged || r.invalid_utf8_output)) process.exitCode=1;

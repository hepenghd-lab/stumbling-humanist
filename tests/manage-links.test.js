'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const { install, remove } = require('../scripts/manage-links');
function fixture(t) {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-local-install-'));
  t.after(() => fs.rmSync(base, { recursive: true, force: true }));
  const root = path.join(base, "source's directory $(literal)");
  const bin = path.join(base, 'bin');
  fs.mkdirSync(path.join(root, 'bin'), { recursive: true }); fs.mkdirSync(bin);
  for (const name of ['codex-zh.js','codex-zh-doctor.js']) fs.writeFileSync(path.join(root,'bin',name), 'console.log(JSON.stringify(process.argv.slice(2)))');
  fs.writeFileSync(path.join(bin, 'codex'), 'official codex stays unchanged');
  const config = path.join(base, 'config.toml');
  fs.writeFileSync(config, '[desktop]\nlocaleOverride="zh-CN"\n');
  return { root, bin, config };
}
test('install/uninstall manages only independent owned links and preserves config', t => {
  const { root, bin, config } = fixture(t);
  const original = fs.readFileSync(config);
  install(root, bin, process.execPath); install(root, bin, process.execPath);
  const result = spawnSync(path.join(bin,'codex-zh-local'), ['hello $(literal)', '你好'], { encoding:'utf8' });
  assert.equal(result.status, 0);
  assert.deepEqual(JSON.parse(result.stdout), ['hello $(literal)', '你好']);
  assert.equal(remove(root).removed.length, 2);
  assert.deepEqual(remove(root), { removed: [], retained: [] });
  assert.deepEqual(fs.readFileSync(config), original);
  assert.equal(fs.readFileSync(path.join(bin,'codex'),'utf8'), 'official codex stays unchanged');
});
test('an unrelated existing launcher is never overwritten, even partially', t => {
  const { root, bin } = fixture(t);
  fs.writeFileSync(path.join(bin,'codex-zh-local-doctor'), 'unrelated');
  assert.throws(() => install(root, bin, process.execPath), /拒绝覆盖/);
  assert.equal(fs.existsSync(path.join(bin,'codex-zh-local')), false);
  assert.equal(fs.readFileSync(path.join(bin,'codex-zh-local-doctor'),'utf8'), 'unrelated');
});
test('uninstall preserves a user-replaced launcher', t => {
  const { root, bin } = fixture(t);
  install(root, bin, process.execPath);
  const link = path.join(bin,'codex-zh-local');
  fs.unlinkSync(link); fs.writeFileSync(link,'user replacement');
  const result = remove(root);
  assert.deepEqual(result.retained, [link]);
  assert.equal(fs.readFileSync(link,'utf8'), 'user replacement');
});

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const overlay = require('../lib/config-overlay');
test('retired config APIs cannot modify an existing user configuration', t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-local-config-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, 'config.toml');
  const original = '[desktop]\nlocaleOverride = "en-US"\nmodel = "original"\n';
  fs.writeFileSync(file, original);
  assert.throws(() => overlay.applyOverlay(file), /disabled/);
  assert.throws(() => overlay.removeOverlay(file), /disabled/);
  assert.equal(fs.readFileSync(file, 'utf8'), original);
  assert.deepEqual(fs.readdirSync(dir), ['config.toml']);
});
test('retired APIs cannot create a configuration file', () => {
  assert.throws(() => overlay.applyOverlay('/unused/not-created.toml'), /disabled/);
  assert.equal(overlay.status(), 'disabled');
});

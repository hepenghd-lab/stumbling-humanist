'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { shouldWrap } = require('../lib/run-mode');
test('redirected input or output bypasses translation', () => {
  assert.equal(shouldWrap([], false, true), false);
  assert.equal(shouldWrap([], true, false), false);
});
test('exec, protocol services, help, version and login bypass even inside a TTY', () => {
  for (const args of [['exec','--json'],['app-server'],['--help'],['-V'],['login'],['resume','--help'],['-m','gpt-6','exec']]) {
    assert.equal(shouldWrap(args, true, true), false, JSON.stringify(args));
  }
});
test('ordinary chat, resume/fork and literal prompts remain interactive', () => {
  for (const args of [[],['resume','--last'],['fork'],['-m','gpt-6','hello'],['--','exec']]) {
    assert.equal(shouldWrap(args, true, true), true);
  }
});

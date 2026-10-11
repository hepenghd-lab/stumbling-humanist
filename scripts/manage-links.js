#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');

const MARKER = '# codex-zh-local launcher';
const NAMES = ['codex-zh-local', 'codex-zh-local-doctor'];
const quote = (text) => "'" + text.replace(/'/g, "'\\''") + "'";
function exists(file) { try { return fs.lstatSync(file); } catch (e) { if (e.code === 'ENOENT') return null; throw e; } }
function ownedLink(link, target) {
  const stat = exists(link);
  return !!stat && stat.isSymbolicLink() && path.resolve(path.dirname(link), fs.readlinkSync(link)) === target;
}

function install(root, binDir, nodeBin) {
  root = fs.realpathSync(root);
  binDir = path.resolve(binDir);
  nodeBin = fs.realpathSync(nodeBin);
  fs.accessSync(nodeBin, fs.constants.X_OK);
  const launcherDir = path.join(root, '.local-launchers');
  const plans = NAMES.map((name, index) => {
    const entry = path.join(root, 'bin', index ? 'codex-zh-doctor.js' : 'codex-zh.js');
    const target = path.join(launcherDir, name);
    const link = path.join(binDir, name);
    const content = '#!/bin/sh\n' + MARKER + '\nexec ' + quote(nodeBin) + ' ' + quote(entry) + ' "$@"\n';
    if (exists(link) && !ownedLink(link, target)) throw new Error('拒绝覆盖已有入口：' + link);
    if (exists(target) && fs.readFileSync(target, 'utf8') !== content) throw new Error('拒绝覆盖已有启动器：' + target);
    return { name, link, target, content };
  });
  fs.mkdirSync(binDir, { recursive: true });
  fs.mkdirSync(launcherDir, { recursive: true });
  const created = [];
  const createdTargets = [];
  const state = path.join(root, '.local-install-state.json');
  const temporary = state + '.tmp-' + process.pid;
  try {
    for (const item of plans) {
      if (!exists(item.target)) {
        fs.writeFileSync(item.target, item.content, { mode: 0o755, flag: 'wx' });
        createdTargets.push(item.target);
      }
      if (!exists(item.link)) {
        fs.symlinkSync(item.target, item.link);
        created.push(item.link);
      }
    }
    fs.writeFileSync(temporary, JSON.stringify({ root, nodeBin, links: plans }, null, 2) + '\n', { mode: 0o600, flag: 'wx' });
    fs.renameSync(temporary, state);
  } catch (error) {
    for (const file of created) fs.unlinkSync(file);
    for (const file of createdTargets) fs.unlinkSync(file);
    if (exists(temporary)) fs.unlinkSync(temporary);
    throw error;
  }
  return plans.map((item) => item.link);
}

function remove(root) {
  root = fs.realpathSync(root);
  const statePath = path.join(root, '.local-install-state.json');
  if (!exists(statePath)) return { removed: [], retained: [] };
  const state = JSON.parse(fs.readFileSync(statePath, 'utf8'));
  if (state.root !== root || !Array.isArray(state.links) || state.links.length !== NAMES.length) {
    throw new Error('安装记录不匹配，未删除任何文件');
  }
  for (const [index, item] of state.links.entries()) {
    if (item.name !== NAMES[index] || path.basename(item.link) !== item.name ||
        item.target !== path.join(root, '.local-launchers', item.name) || typeof item.content !== 'string' ||
        !item.content.startsWith('#!/bin/sh\n' + MARKER + '\n')) {
      throw new Error('安装记录无效，未删除任何文件');
    }
  }
  const removed = [], retained = [];
  for (const item of state.links) {
    if (ownedLink(item.link, item.target)) { fs.unlinkSync(item.link); removed.push(item.link); }
    else if (exists(item.link)) retained.push(item.link);
    if (exists(item.target) && fs.readFileSync(item.target, 'utf8') === item.content) fs.unlinkSync(item.target);
  }
  fs.unlinkSync(statePath);
  return { removed, retained };
}

if (require.main === module) {
  try {
    const root = path.resolve(__dirname, '..');
    const action = process.argv[2];
    if (action === 'install') console.log(JSON.stringify(install(root, process.argv[3] || path.join(os.homedir(), '.local', 'bin'), process.argv[4] || process.execPath)));
    else if (action === 'remove') console.log(JSON.stringify(remove(root)));
    else throw new Error('用法：manage-links.js install|remove');
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}

module.exports = { install, remove };

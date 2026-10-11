#!/usr/bin/env node
'use strict';
const { spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const detect = require('../lib/detect');
const { UiMatcher } = require('../lib/ui-matcher');
let failed = false;
function check(label, run) {
  try { const result=run(); console.log('✔ '+label+(result?'：'+result:'')); }
  catch(error) { failed=true; console.error('✘ '+label+'：'+error.message); }
}
check('Node.js 18+',()=>{if(Number(process.versions.node.split('.')[0])<18)throw Error('版本过低');return process.version;});
check('Python 3',()=>{const r=spawnSync(process.env.CODEX_ZH_PYTHON||'python3',['--version'],{encoding:'utf8',timeout:5000});if(r.error||r.status!==0)throw Error('无法启动 Python 3');return r.stdout.trim();});
check('官方 Codex 入口',()=>{const bin=detect.resolveCodexBin();if(!bin)throw Error('未找到');return bin;});
check('官方 Codex 版本',()=>{const v=detect.getCodexVersion();if(!v)throw Error('无法读取');return v+'（本地开发基线：0.162.1）';});
check('A～E 翻译词表',()=>{const data=JSON.parse(fs.readFileSync(path.join(__dirname,'..','data','ui-translations-local.json'),'utf8'));new UiMatcher(data);return data.length+' 项';});
console.log('此检查不会修改官方入口、登录信息或 Codex 配置。');
process.exitCode=failed?1:0;


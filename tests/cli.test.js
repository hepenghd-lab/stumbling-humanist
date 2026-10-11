'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('fs');const path=require('path');const os=require('os');
const {spawnSync}=require('child_process');
test('non-interactive CLI preserves stdout JSON, stderr, args and exit status',t=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'codex-local-cli-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
  const binary=path.join(dir,'codex-fixture');
  fs.writeFileSync(binary,'#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps({"status":"Working","args":sys.argv[1:]}))\nprint("Failed",file=sys.stderr)\nsys.exit(7)\n',{mode:0o755});
  const args=['exec','--json','literal $(value)','你好'];
  const result=spawnSync(process.execPath,[path.join(__dirname,'..','bin','codex-zh.js'),'--codex-bin',binary,...args],{encoding:'utf8'});
  assert.equal(result.status,7);assert.deepEqual(JSON.parse(result.stdout),{status:'Working',args});assert.equal(result.stderr,'Failed\n');
});

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { stripVTControlCharacters } = require('node:util');
const pty = require('../lib/pty-bridge');
function execute(script, interact) {
  return new Promise((resolve, reject) => {
    let out = '', error = '';
    const child = pty.spawn(process.execPath, ['-e',script], { cwd:process.cwd(), env:{...process.env,TERM:'xterm-256color'},cols:80,rows:24 });
    const timeout = setTimeout(() => { child.kill('SIGKILL'); reject(Error('PTY timeout: '+out+' '+error)); }, 4000);
    child.onError(msg => { error += msg; });
    child.onData(text => { out += text; if(interact)interact(child,out); });
    child.onExit(status => { clearTimeout(timeout); resolve({out,error,...status}); });
  });
}
test('POSIX transport creates a real TTY and preserves ANSI/Unicode/exit code', { skip:process.platform==='win32' }, async () => {
  const result = await execute('console.log(process.stdout.isTTY,process.stdout.columns,process.stdout.rows);process.stdout.write("\\x1b[1mExplored\\x1b[0m 中文🌟\\n");process.exitCode=7');
  assert.match(stripVTControlCharacters(result.out),/true 80 24/);
  assert.ok(result.out.includes('\x1b[1mExplored\x1b[0m 中文🌟'));
  assert.equal(result.exitCode,7); assert.equal(result.signal,0); assert.equal(result.error,'');
});
test('terminal resize reaches the child process', { skip:process.platform==='win32' }, async () => {
  let sent = false;
  const result = await execute('process.stdout.on("resize",()=>{console.log("SIZE",process.stdout.columns,process.stdout.rows);process.exit(0)});console.log("READY");setInterval(()=>{},1000)', (child,out) => {
    if(!sent&&out.includes('READY')){sent=true;child.resize(100,40);}
  });
  assert.match(stripVTControlCharacters(result.out),/SIZE 100 40/); assert.equal(result.exitCode,0);
});
test('signals terminate the child and preserve the signal number', { skip:process.platform==='win32' }, async () => {
  let sent = false;
  const result = await execute('console.log("READY");setInterval(()=>{},1000)', (child,out) => {
    if(!sent&&out.includes('READY')){sent=true;child.kill('SIGTERM');}
  });
  assert.equal(result.signal,15);
});
test('large terminal output is drained without truncation', { skip:process.platform==='win32' }, async () => {
  const result = await execute('process.stdout.write("x".repeat(262144));');
  assert.equal(result.out.length,262144); assert.equal(result.exitCode,0);
});
test('UTF-8 input and output retain split multibyte characters', { skip:process.platform==='win32' }, async () => {
  let sent=false;
  const result=await execute('process.stdin.setRawMode(true);let input=Buffer.alloc(0);process.stdin.on("data",b=>{input=Buffer.concat([input,b]);if(input.length===6){process.stdout.write("ECHO "+input.toString());process.exit(0)}});console.log("READY")',(child,out)=>{
    if(!sent&&out.includes('READY')){sent=true;const bytes=Buffer.from('你好');child.write(bytes.subarray(0,1));child.write(bytes.subarray(1));}
  });
  assert.ok(result.out.includes('ECHO 你好')); assert.equal(result.exitCode,0);
});

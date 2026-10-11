'use strict';

const NON_INTERACTIVE = new Set([
  'agents', 'exec', 'e', 'review', 'login', 'logout', 'mcp', 'plugin',
  'app-server', 'remote-control', 'app', 'completion', 'update', 'doctor',
  'sandbox', 'debug', 'apply', 'a', 'queue', 'archive', 'delete',
  'migrate-rollouts', 'unarchive', 'cloud', 'exec-server', 'features', 'help',
]);
const VALUES = new Set([
  '-c', '--config', '--enable', '--disable', '--remote', '--remote-auth-token-env',
  '-i', '--image', '-m', '--model', '--local-provider', '-p', '--profile',
  '-s', '--sandbox', '-C', '--cd', '--add-dir', '-a', '--ask-for-approval',
]);

/** Bypass translation AND the extra PTY for non-interactive execution. */
function shouldWrap(argv, stdinTTY, stdoutTTY) {
  if (!stdinTTY || !stdoutTTY) return false;
  let firstPositional = null;
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--') break;
    if (['--help', '-h', '--version', '-V'].includes(arg)) return false;
    if (VALUES.has(arg)) { i += 1; continue; }
    if (arg.startsWith('-')) continue;
    if (firstPositional === null) firstPositional = arg;
    if (NON_INTERACTIVE.has(firstPositional)) return false;
  }
  return true;
}

module.exports = { shouldWrap };

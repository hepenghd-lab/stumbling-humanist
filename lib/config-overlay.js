'use strict';
// Retired: this local fork never writes, deletes, restores or backs up Codex config.
const retired = () => { throw new Error('Codex configuration changes are disabled in this local fork'); };
module.exports = { applyOverlay: retired, removeOverlay: retired, status: () => 'disabled' };


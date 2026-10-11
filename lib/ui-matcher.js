'use strict';

const { stringWidth, padToWidth } = require('./width');
const { escapeRegex } = require('./matcher');

/** Match only a complete allowlisted UI fragment, never a substring in prose. */
class UiMatcher {
  constructor(entries) {
    this.entries = entries.map((entry) => {
      if (!entry || typeof entry.en !== 'string' || typeof entry.zh !== 'string' || !entry.en.trim()) {
        throw new Error('Invalid UI translation entry');
      }
      const names = [...entry.en.matchAll(/\$\{([^}]+)\}/g)].map((m) => m[1]);
      const zhNames = [...entry.zh.matchAll(/\$\{([^}]+)\}/g)].map((m) => m[1]);
      if (JSON.stringify([...names].sort()) !== JSON.stringify([...zhNames].sort())) {
        throw new Error('Placeholder mismatch: ' + entry.en);
      }
      const parts = entry.en.split(/\$\{[^}]+\}/g);
      let pattern = '^';
      parts.forEach((part, i) => {
        pattern += escapeRegex(part);
        if (i < names.length) pattern += names[i] === 'detail' ? '(.*)' : '(-?\\d+)';
      });
      pattern += '$';
      return { ...entry, names, regex: new RegExp(pattern, 'u') };
    });
  }

  match(text) {
    const pieces = /^([\s•·│└├─↳✘✗⚠›]*(?:\d+[.)] +)?)(.*?)(\s*)$/u.exec(text);
    if (!pieces) return null;
    const [, prefix, core, suffix] = pieces;
    for (const entry of this.entries) {
      let match = entry.regex.exec(core);
      let adornment = '';
      if (!match && entry.id && entry.id.startsWith('D')) {
        const key = /^(.*?)(\s+\([A-Za-z]\))$/.exec(core);
        if (key) { match = entry.regex.exec(key[1]); if (match) adornment = key[2]; }
      }
      if (!match) {
        const ellipsis = /^(.*?)(\.\.\.|…)$/.exec(core);
        if (ellipsis) { match = entry.regex.exec(ellipsis[1]); if (match) adornment = ellipsis[2]; }
      }
      if (!match) continue;
      let zh = entry.zh;
      entry.names.forEach((name, i) => { zh = zh.split('${' + name + '}').join(match[i + 1]); });
      zh += adornment;
      const available = stringWidth(core + suffix);
      const need = Math.max(0, stringWidth(zh) - available);
      return { need, original: text, prefix, zh, available };
    }
    return null;
  }

  render(match, donatedSpaces = 0) {
    return match.prefix + padToWidth(match.zh, match.available + donatedSpaces);
  }
}

module.exports = { UiMatcher };

'use strict';
const { stringWidth, padToWidth } = require('./width');
const { escapeRegex } = require('./matcher');
const ACTIONS = ['Searching page','Searched page','Searching for','Searched for','You ran','Exploring','Explored','Running','Calling','Called','Search','Read','List','Run','Ran'];
const TIMER = '\\d+(?:h \\d{2}m \\d{2}s|m \\d{2}s|s)';
const KEY = '(?:esc|tab|enter|ctrl\\+[a-z]|shift\\+tab|f\\d{1,2}|←|\\?)';

class UiMatcher {
  constructor(entries) {
    this.entries = entries.map(entry => {
      if (!entry || typeof entry.en !== 'string' || typeof entry.zh !== 'string' || !entry.en.trim()) throw new Error('Invalid UI translation entry');
      const names = [...entry.en.matchAll(/\$\{([^}]+)\}/g)].map(m => m[1]);
      const zhNames = [...entry.zh.matchAll(/\$\{([^}]+)\}/g)].map(m => m[1]);
      if (JSON.stringify([...names].sort()) !== JSON.stringify([...zhNames].sort())) throw new Error('Placeholder mismatch: ' + entry.en);
      const parts = entry.en.split(/\$\{[^}]+\}/g);
      let pattern = '^';
      parts.forEach((part,i) => { pattern += escapeRegex(part); if (i < names.length) pattern += names[i] === 'detail' ? '(.*)' : '(-?\\d+)'; });
      return { ...entry, names, regex: new RegExp(pattern + '$', 'u') };
    });
  }
  _lookup(core) {
    for (const entry of this.entries) {
      let match = entry.regex.exec(core), adornment = '';
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
      entry.names.forEach((name,i) => { zh = zh.split('${' + name + '}').join(match[i + 1]); });
      return zh + adornment;
    }
    return null;
  }
  _edit(text, start, end, en) {
    const zh = this._lookup(en);
    if (zh === null) return null;
    const available = stringWidth(text.slice(start,end));
    if (stringWidth(zh) > available) return null;
    return { start, end, replacement: padToWidth(zh, available) };
  }
  match(text, context = {}) {
    const pieces = /^([\s•·│└├─↳✘✗⚠›\u2800-\u28ff]*(?:\d+[.)] +)?)(.*?)(\s*)$/u.exec(text);
    if (!pieces) return null;
    const [, prefix, core] = pieces;
    const exact = this._lookup(core);
    if (exact !== null) {
      const edit = this._edit(text, prefix.length, text.length, core);
      return { edits: edit ? [edit] : [], fallbacks: edit ? 0 : 1 };
    }
    const command = /^(\/(?:init|status|permissions|model|review) - )(.+)$/.exec(core);
    if (command) return { edits: [this._edit(text,prefix.length+command[1].length,text.length,command[2])].filter(Boolean) };
    // Protect visibly structured code before considering other UI grammars.
    if (/^\s*(?:[{$#!/\\]|print\(|const\b|let\b|var\b)/.test(text)) return null;
    const working = new RegExp('^Working \\((' + TIMER + ')(?: • (' + KEY + ') (to interrupt))?\\)(?: · .+)?$', 'i').exec(core);
    if (working) {
      const edits = [this._edit(text,prefix.length,prefix.length+7,'Working')];
      if (working[3]) {
        const start = prefix.length + core.indexOf(' to interrupt') + 1;
        edits.push(this._edit(text,start,start+12,'to interrupt'));
      }
      return { edits: edits.filter(Boolean) };
    }
    const completed = new RegExp('^Worked for ' + TIMER + ' • \\d{2}:\\d{2}$').exec(core);
    if (completed) return { edits: [this._edit(text,prefix.length,prefix.length+10,'Worked for')].filter(Boolean) };
    for (const action of ACTIONS) {
      if (!core.startsWith(action + ' ')) continue;
      if (!/[•\u2800-\u28ff]/u.test(prefix + (context.rowPrefix || '')) && !context.styled) continue;
      const gaps = /^ +/.exec(core.slice(action.length))[0].length;
      let start = prefix.length, end = start + action.length;
      const zh = this._lookup(action);
      const need = zh === null ? Infinity : Math.max(0,stringWidth(zh)-stringWidth(action));
      if (need) {
        if (gaps > need || context.styled && !prefix || context.virtualGaps && gaps >= need) end += need;
        else if (prefix.endsWith(' '.repeat(need))) start -= need;
        else return { edits: [], fallbacks: 1 };
      }
      const edit = this._edit(text,start,end,action);
      return { edits: edit ? [edit] : [], fallbacks: edit ? 0 : 1 };
    }
    // Entire footer must consist of known key/hint atoms, not arbitrary prose.
    const footer = text.trim();
    const atoms = footer.split(' · ');
    const pattern = new RegExp('^(' + KEY + ') +(for agents|for shortcuts|to queue message|to queue|again to quit|to edit previous message|to view)$','i');
    if (atoms.every(atom => pattern.test(atom))) {
      let offset = text.indexOf(footer);
      const edits = [];
      for (const atom of atoms) {
        const match = pattern.exec(atom), hint = match[2], start = offset + atom.length - hint.length;
        const edit = this._edit(text,start,start+hint.length,hint);
        if (edit) edits.push(edit);
        offset += atom.length + 3;
      }
      return { edits };
    }
    const warning = /^(\d+ warnings?)( · f\d{1,2} to view)?$/.exec(core);
    if (warning) {
      const edits = [this._edit(text,prefix.length,prefix.length+warning[1].length,warning[1])];
      if (warning[2]) {
        const start = prefix.length + core.lastIndexOf('to view');
        edits.push(this._edit(text,start,start+7,'to view'));
      }
      return { edits: edits.filter(Boolean) };
    }
    return null;
  }
}
module.exports = { UiMatcher };

#!/usr/bin/env node
'use strict';
const fs = require('fs');
const path = require('path');
const { UiMatcher } = require('../lib/ui-matcher');
const { stringWidth } = require('../lib/width');
const entries = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'ui-translations-local.json'), 'utf8'));
new UiMatcher(entries);
const expected = ['A1','A2','A3','A4','A5','A6','A7','B1','B2','B3','B4','B5','B6','C1','C2','C3','C4','D1','D2','D3','D4','E1','E2','E3','E4','F1','F2','F3','F4','F5','F6'];
const ids = new Set(entries.map(e => e.id));
const missing = expected.filter(id => !ids.has(id));
const keys = new Set();
for (const e of entries) {
  if (keys.has(e.en)) throw new Error('Duplicate translation: '+e.en);
  keys.add(e.en);
}
if (missing.length) throw new Error('Missing approved groups: '+missing.join(', '));
const needsPadding = entries.filter(e => !e.en.includes('${') && stringWidth(e.zh)>stringWidth(e.en));
console.log(`Validated ${entries.length} entries, ${ids.size} approved groups; ${needsPadding.length} short labels use adjacent padding or retain English.`);


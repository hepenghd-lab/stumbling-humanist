'use strict';
const { AnsiTokenizer } = require('../lib/ansi-tokenizer');
const { stringWidth } = require('../lib/width');
// A limited text-cell emulator for CUP/EL/ED/SGR replay assertions, not a full terminal.
function screen(input, rows = 50, columns = 140) {
  const cells = Array.from({ length: rows }, () => Array(columns).fill(' '));
  const history = [];
  let row = 0, column = 0;
  const tokenizer = new AnsiTokenizer({
    onText(text) {
      for (const character of text) {
        const width = stringWidth(character);
        if (!width) continue;
        if (column + width > columns) { column = 0; row += 1; }
        if (row >= rows) { cells.shift(); cells.push(Array(columns).fill(' ')); row = rows - 1; }
        cells[row][column] = character;
        for (let n = 1; n < width; n++) cells[row][column+n] = '';
        column += width;
      }
    },
    onRaw(raw) {
      if (raw === '\r') column = 0;
      if (raw === '\n') row = Math.min(rows-1,row+1);
      const pos = /^\x1b\[(\d*)(?:;(\d*))?[Hf]$/.exec(raw);
      if (pos) { history.push(cells[row].join('').trimEnd()); row = Math.min(rows-1,(Number(pos[1])||1)-1); column = Math.min(columns-1,(Number(pos[2])||1)-1); }
      const move = /^\x1b\[(\d*)([ABCG])$/.exec(raw);
      if (move) { const n=Number(move[1])||1; if (move[2]==='A') row=Math.max(0,row-n); if (move[2]==='B') row=Math.min(rows-1,row+n); if (move[2]==='C') column=Math.min(columns-1,column+n); if (move[2]==='G') column=Math.min(columns-1,n-1); }
      const erase = /^\x1b\[(\d*)K$/.exec(raw);
      if (erase) { const n=Number(erase[1]); for (let c=n===1||n===2?0:column;c<(n===1?column+1:columns);c++) cells[row][c]=' '; }
      const eraseScreen = /^\x1b\[(\d*)J$/.exec(raw);
      if (eraseScreen) {
        const mode = Number(eraseScreen[1]);
        if (mode === 2) for (const line of cells) line.fill(' ');
        if (mode === 0) { cells[row].fill(' ',column); for (let r=row+1;r<rows;r++) cells[r].fill(' '); }
        if (mode === 1) { cells[row].fill(' ',0,column+1); for (let r=0;r<row;r++) cells[r].fill(' '); }
      }
    }
  });
  tokenizer.feed(input); tokenizer.end();
  const result = cells.map(line=>line.join('').trimEnd());
  result.history = history;
  return result;
}
module.exports = { screen };

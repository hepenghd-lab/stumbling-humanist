'use strict';
const { AnsiTokenizer } = require('./ansi-tokenizer');
const { UiMatcher } = require('./ui-matcher');
const { stringWidth } = require('./width');

// Buffer a printable render segment across SGR changes, not across cursor moves.
// This handles per-letter shimmer without inventing or deleting control bytes.
class StreamTranslator {
  constructor(entries, write, opts = {}) {
    this.write = write;
    this.enabled = opts.enabled !== false;
    this.onBeforeText = opts.onBeforeText || null;
    this.matcher = new UiMatcher(entries);
    this.flushIntervalMs = opts.flushIntervalMs ?? 25;
    if (!Number.isFinite(this.flushIntervalMs) || this.flushIntervalMs < 0) throw new Error('flushIntervalMs must be finite and non-negative');
    this._schedule = opts.schedule || setTimeout;
    this._cancel = opts.cancel || clearTimeout;
    this._timer = null;
    this._events = [];
    this._text = '';
    this._bufferSize = 0;
    this._protectedLine = false;
    this._inCodeFence = false;
    this._rowText = '';
    this._row = 1;
    this._column = 1;
    this._ended = false;
    this.stats = { inBytes: 0, outBytes: 0, hits: 0, runs: 0, widthFallbacks: 0 };
    this.tokenizer = new AnsiTokenizer({ onText: text => this._onText(text), onRaw: bytes => this._onRaw(bytes) });
  }
  _emit(text) {
    this.stats.outBytes += Buffer.byteLength(text);
    this.write(text);
  }
  _onText(text) {
    this.stats.runs += 1;
    if (this.onBeforeText) {
      const replacement = this.onBeforeText(text);
      if (typeof replacement === 'string') text = replacement;
    }
    this._events.push({ text });
    this._text += text;
    this._bufferSize += text.length;
    if (this._bufferSize > 65536) this._flushSegment();
  }
  _newRow() {
    this._protectedLine = false;
    this._rowText = '';
  }
  _trackControl(bytes) {
    if (bytes === '\n' || bytes === '\v' || bytes === '\f') { this._row += 1; this._newRow(); }
    if (bytes === '\r') { this._column = 1; this._newRow(); }
    const position = /^\x1b\[(\d*)(?:;(\d*))?[Hf]$/.exec(bytes);
    if (position) {
      const row = Number(position[1]) || 1, column = Number(position[2]) || 1;
      if (row !== this._row || column === 1) this._newRow();
      this._row = row; this._column = column;
    }
    const vertical = /^\x1b\[(\d*)[ABEFd]$/.exec(bytes);
    if (vertical) { this._newRow(); this._row = null; }
    const horizontal = /^\x1b\[(\d*)([CDG])$/.exec(bytes);
    if (horizontal) {
      const amount = Number(horizontal[1]) || 1;
      this._column = horizontal[2] === 'G' ? amount
        : horizontal[2] === 'D' ? Math.max(1, this._column - amount) : this._column + amount;
      // Horizontal moves preserve protection: styled code can continue here.
    }
    if (bytes === '\x1bD' || bytes === '\x1bE' || bytes === '\x1bM') { this._newRow(); this._row = null; }
    if (/^\x1b\[(?:2J|\?(?:1049|47|1047)[hl])$/.test(bytes)) {
      this._newRow(); this._inCodeFence = false; this._row = null;
    }
  }
  _onRaw(bytes) {
    if (/^\x1b\[[0-9;:]*m$/.test(bytes)) {
      this._events.push({ raw: bytes });
      this._bufferSize += bytes.length;
      if (this._bufferSize > 65536) this._flushSegment();
      return;
    }
    // Ratatui omits blank cells and positions the cursor at the next word.
    // Join only small forward gaps on the same row; preserve every cursor byte.
    const position = /^\x1b\[(\d*)(?:;(\d*))?[Hf]$/.exec(bytes);
    const column = /^\x1b\[(\d*)([CG])$/.exec(bytes);
    const current = this._column + stringWidth(this._text);
    const target = position && (Number(position[1]) || 1) === this._row
      ? (Number(position[2]) || 1)
      : column ? column[2] === 'G' ? (Number(column[1]) || 1) : current + (Number(column[1]) || 1) : null;
    if (this._events.length && target !== null && target >= current && target - current <= 16) {
      const gap = ' '.repeat(target - current);
      this._events.push({ text: gap, virtual: true }, { raw: bytes, cursor: true });
      this._text += gap;
      this._bufferSize += gap.length + bytes.length;
      if (this._bufferSize > 65536) this._flushSegment();
      return;
    }
    this._flushSegment();
    this._emit(bytes);
    this._trackControl(bytes);
  }
  _render(edits) {
    let position = 0;
    const boundaries = [];
    for (const event of this._events) {
      if (event.text !== undefined) position += event.text.length;
      if (event.cursor) boundaries.push(position);
    }
    const clipped = [];
    for (const edit of edits) {
      const cuts = [edit.start, ...boundaries.filter(n => n > edit.start && n < edit.end), edit.end];
      const parts = [];
      for (let n = 1; n < cuts.length; n++) {
        const from = stringWidth(this._text.slice(edit.start, cuts[n - 1]));
        const to = stringWidth(this._text.slice(edit.start, cuts[n]));
        let cell = 0, replacement = '', valid = true;
        for (const character of edit.replacement) {
          const next = cell + stringWidth(character);
          if (cell < from && next > from || cell < to && next > to) valid = false;
          if (cell >= from && next <= to) replacement += character;
          cell = next;
        }
        if (!valid) { parts.length = 0; break; }
        parts.push({ start: cuts[n - 1], end: cuts[n], replacement });
      }
      if (parts.length) clipped.push(...parts);
      else { this.stats.widthFallbacks += 1; this.stats.hits -= 1; }
    }
    edits = clipped;
    let offset = 0, editIndex = 0;
    for (const event of this._events) {
      if (event.raw !== undefined) { this._emit(event.raw); continue; }
      const end = offset + event.text.length;
      let pos = offset;
      while (pos < end) {
        while (editIndex < edits.length && edits[editIndex].end <= pos) editIndex += 1;
        const edit = edits[editIndex];
        if (edit && pos >= edit.start) {
          if (pos === edit.start) this._emit(edit.replacement);
          pos = Math.min(end, edit.end);
        } else {
          const stop = edit ? Math.min(end, edit.start) : end;
          if (!event.virtual) this._emit(event.text.slice(pos - offset, stop - offset));
          pos = stop;
        }
      }
      offset = end;
    }
  }
  _flushSegment() {
    if (!this._events.length) return;
    const text = this._text;
    const fences = text.match(/```/g);
    const fenced = this._inCodeFence || Boolean(fences);
    if (fences && fences.length % 2) this._inCodeFence = !this._inCodeFence;
    const styled = this._events.some(e => e.raw !== undefined);
    let edits = [];
    if (text && this.enabled && !this._protectedLine && !fenced) {
      const match = this.matcher.match(text, { styled, rowPrefix: this._rowText,
        virtualGaps: this._events.some(event => event.virtual) });
      if (match) {
        edits = match.edits;
        this.stats.widthFallbacks += match.fallbacks || 0;
        this.stats.hits += edits.length;
      }
    }
    this._render(edits);
    if (!edits.length && (fenced || /[{}\[\]();="`]/.test(text) || /^\s*[$#!/\\-]/.test(text))) this._protectedLine = true;
    this._rowText = (this._rowText + text).slice(0, 512);
    this._column += stringWidth(text);
    this._events = []; this._text = ''; this._bufferSize = 0;
  }
  _startTimer() {
    if (this._timer !== null || this.flushIntervalMs === 0) return;
    this._timer = this._schedule(() => { this._timer = null; this._flush(); }, this.flushIntervalMs);
    if (this._timer && this._timer.unref) this._timer.unref();
  }
  _flush() { this.tokenizer.flushText(0); this._flushSegment(); }
  feed(chunk) {
    if (!chunk || this._ended) return;
    this.stats.inBytes += Buffer.byteLength(chunk);
    this.tokenizer.feed(chunk);
    if (this.tokenizer.pending.length > 65536) this._flush();
    this._startTimer();
  }
  end() {
    if (this._ended) return;
    this._ended = true;
    if (this._timer !== null) this._cancel(this._timer);
    this._timer = null;
    this.tokenizer.end(); this._flushSegment();
  }
}
module.exports = { StreamTranslator };

'use strict';

const { AnsiTokenizer } = require('./ansi-tokenizer');
const { UiMatcher } = require('./ui-matcher');

/**
 * Complete allowlisted UI fragments only; no general prose substitution.
 * Short Chinese labels may borrow existing adjacent ASCII padding, across SGR
 * style changes. Cursor controls are never rewritten. If padding is insufficient,
 * retain English rather than overwrite a neighbouring field. All buffered output
 * is released within one flush interval, including unterminated prompts.
 * Standalone allowlisted words in ordinary prose remain an acknowledged ambiguity.
 */
class StreamTranslator {
  constructor(entries, write, opts = {}) {
    this.write = write;
    this.enabled = opts.enabled !== false;
    this.onBeforeText = opts.onBeforeText || null;
    this.matcher = new UiMatcher(entries);
    this.flushIntervalMs = opts.flushIntervalMs ?? 25;
    if (!Number.isFinite(this.flushIntervalMs) || this.flushIntervalMs < 0) {
      throw new Error('flushIntervalMs must be finite and non-negative');
    }
    this._schedule = opts.schedule || setTimeout;
    this._cancel = opts.cancel || clearTimeout;
    this._timer = null;
    this._pending = null;
    this._protectedLine = false;
    this._inCodeFence = false;
    this._ended = false;
    this.stats = { inBytes: 0, outBytes: 0, hits: 0, runs: 0, widthFallbacks: 0 };
    this.tokenizer = new AnsiTokenizer({
      onText: (text) => this._onText(text),
      onRaw: (bytes) => this._onRaw(bytes),
    });
  }

  _emit(text) {
    this.stats.outBytes += Buffer.byteLength(text);
    this.write(text);
  }

  _releasePending(spaces = null) {
    const pending = this._pending;
    if (!pending) return;
    this._pending = null;
    if (spaces === null) {
      this._emit(pending.match.original);
      this.stats.widthFallbacks += 1;
    } else {
      this._emit(this.matcher.render(pending.match, spaces));
      this.stats.hits += 1;
    }
    this._emit(pending.raw);
  }

  _onRaw(bytes) {
    if (this._pending && /^\x1b\[[0-9;:]*m$/.test(bytes)) {
      this._pending.raw += bytes;
      if (this._pending.raw.length > 65536) this._releasePending();
      return;
    }
    this._releasePending();
    this._emit(bytes);
    if (/[\r\n]/.test(bytes)) this._protectedLine = false;
  }

  _onText(text) {
    this.stats.runs += 1;
    if (this._pending) {
      const spaces = /^ */.exec(text)[0].length;
      const need = this._pending.match.need;
      if (this.enabled && spaces >= need) {
        this._releasePending(need);
        text = text.slice(need);
      } else {
        this._releasePending();
      }
    }
    if (!text) return;
    if (this.onBeforeText) {
      const replacement = this.onBeforeText(text);
      if (typeof replacement === 'string') text = replacement;
    }
    const fences = text.match(/```/g);
    if (fences) {
      if (fences.length % 2) this._inCodeFence = !this._inCodeFence;
      this._protectedLine = true;
    }
    if (this.enabled && !this._protectedLine && !this._inCodeFence) {
      const match = this.matcher.match(text);
      if (match) {
        if (match.need === 0) {
          this._emit(this.matcher.render(match));
          this.stats.hits += 1;
        } else {
          this._pending = { match, raw: '' };
        }
        return;
      }
    }
    if (/[{}\[\]();="`]/.test(text) || /^\s*[$#!/\\-]/.test(text)) {
      this._protectedLine = true;
    }
    this._emit(text);
  }

  _startTimer() {
    if (this._timer !== null || this.flushIntervalMs === 0) return;
    this._timer = this._schedule(() => {
      this._timer = null;
      this._flush();
    }, this.flushIntervalMs);
    if (this._timer && this._timer.unref) this._timer.unref();
  }

  _flush() {
    this.tokenizer.flushText(0);
    this._releasePending();
  }

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
    this.tokenizer.end();
    this._releasePending();
  }
}

module.exports = { StreamTranslator };

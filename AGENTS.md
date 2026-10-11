# codex-zh-local

This is a local MIT-licensed fork of taekchef/codex-code-zh-cn v1.2.0, pinned upstream commit d5c554a860ed22483a49c820283439c9eb23746e.

## Scope and architecture

- Translate only the explicitly approved A–E UI elements in data/ui-translations-local.json. This file is the sole active translation source; older data/verbs/tips files are historical reference and are not loaded.
- UiMatcher matches complete allowlisted fragments and preserves dynamic fields. Never add generic substring translation of prose, commands, JSON or paths.
- StreamTranslator passes control bytes through, protects obvious code and fenced blocks, and flushes pending output within 25 ms. Short labels may consume existing adjacent spaces; without enough space retain English.
- The semantic source of PTY output is unknowable. Document residual ambiguity rather than claiming perfect separation of UI and model/tool output.
- Non-interactive commands, help/version, and redirected streams bypass translation and the extra PTY.
- lib/pty-bridge.js and scripts/pty_bridge.py use Node.js and Python standard libraries. Do not add download-on-install scripts or native npm dependencies without a concrete need.
- Never shadow official codex or alter ~/.codex/config.toml/auth/session data. Retired desktop configuration and shadow scripts must remain disabled.
- Installer operates only on this local checkout and creates independent codex-zh-local launchers. Uninstaller removes only recorded, still-owned launchers and retains user-replaced files.
- Preserve the upstream MIT license. Do not claim translations were copied from OALD 10 bilingual entries when only public Oxford online English definitions were available.

## Verification

Run node --test and node scripts/validate-data.js (equivalent to npm test / npm run lint), using an explicit trusted Node binary if node is absent from PATH. Run bash -n install.sh uninstall.sh and Python syntax checks. Cover code preservation, ANSI sequences, all A–E entries, finite output flush, PTY I/O/resizes/signals/exit codes, non-interactive byte preservation, and ownership-aware install/uninstall.

Do not install globally, publish or push merely to validate a source change. Report actual validation scope and remaining limitations.


# Open Source Readiness

Updated: 2026-04-22

This is the current reality check for publishing Mogger Mon as a public repository instead of a private launch sandbox.

## Done

- Visible project branding is now `Mogger Mon` across the main app shell, package metadata, docs, and script names.
- The startup flow is local-first and no longer depends on login or the old first-run gender prompt.
- Public-facing battle/item wording has been rethemed toward `Mogger Mon`, `Mogmaster`, `Maxx`, `Cryotank`, `BrainDance`, and `Zaza`.
- A clean redraw source pack exists at [output/original-art-redo-pack](../output/original-art-redo-pack).
  - Current pack size: 32,517 files.
  - Major image buckets: 25,679 species/icon candidates, 1,561 UI files, 923 battle-animation JSON files, 646 battle-animation image sheets, 614 trainer files, 529 item files, 190 arena files, and 26 egg files.
  - The first generated Grok redo batch is retained in `output/original-art-redo-pack/grok` with 1,351 files.
- Upstream contributor, credit, funding, and deploy docs have been replaced or removed for a source-neutral public repo.
- The `assets` and `locales` submodules have launch-clean commits.
- Private source prompts, wiki reference caches, and raw TCG/reference caches have been moved under ignored `output/private-generation-prompts`.
- `.env.example` exists, and checked-in env presets are documented as local-first guest-play presets.

## Publish Blockers

- Asset provenance is still mixed.
  - See [COMMERCIAL_ASSET_SWEEP.md](../COMMERCIAL_ASSET_SWEEP.md).
  - See [COMMERCIAL_ASSET_REPLACE_MANIFEST.tsv](../COMMERCIAL_ASSET_REPLACE_MANIFEST.tsv).
  - See [COMMERCIAL_MOVE_CONTENT_SWEEP.md](../COMMERCIAL_MOVE_CONTENT_SWEEP.md).
- The runtime still uses the inherited `images/pokemon` species/icon folder layout inside the assets submodule. Branding is now Mogger Mon, but the path migration has not been completed because the engine still references those paths.
- Audio remains only partially de-risked.
  - Core launch SFX were refreshed.
  - The Fal MPP audio redo pack currently has generated replacements for 37/37 `se`, 3/3 `ui`, and 827/1,310 `battle_anims` source files.
  - Generated audio is retained under `output/original-art-redo-pack/audio/fal-mpp`, but the long-tail generated replacements have not been installed into `assets/audio`.
  - Full BGM, cries, and the remaining battle SFX still need provenance review or replacement.
- App-specific host integration details still need a public-source decision.
  - [src/tempaitown-host.ts](../src/tempaitown-host.ts) should either stay documented as an optional embed path or be isolated behind clearer standalone defaults.

## Strongly Recommended Before Publishing

- Decide whether the inherited `images/pokemon` species/icon folder layout will stay as an implementation detail or be fully migrated to a Mogger Mon-native path.
- Replace or remove any remaining inherited trainer, item, move-VFX, and audio assets that are only partially transformed.
- Run a final real-browser smoke pass over Guest Mode, Aura login, starter select, Battle Lab, Move Lab, and one complete battle.

## Nice To Have

- Keep private prompt history out of public docs unless it is rewritten as source-neutral Mogger Mon process documentation.
- Add a narrower OSS-facing README for the `assets` and `locales` submodules.
- Collapse scratch pipeline outputs behind stronger ignore rules or a separate artifacts directory.

## Suggested Publish Order

1. Lock down the remaining audio and asset provenance questions.
2. Decide whether to migrate the legacy species asset paths now or document them as implementation detail.
3. Publish from a clean root + submodule state after a final production build and browser smoke test.

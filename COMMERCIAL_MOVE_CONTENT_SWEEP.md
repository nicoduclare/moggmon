# Commercial Move Content Sweep

Generated: 2026-04-05

This sweep covers move-related source and locale files. Asset-side move animation JSON and audio remain covered by `COMMERCIAL_ASSET_REPLACE_MANIFEST.tsv`.

## Bottom Line

- Candidate move-sensitive files scanned: 262
- Replace-now files: 49
- Engine or rules files requiring audit/remap: 181

## Replace Buckets

- `REPLACE_MOVE_TEXT`: 34
- `REPLACE_MOVE_BALANCE`: 5
- `REPLACE_MOVE_SPECIES_MAPPING`: 5
- `REPLACE_MOVE_CATALOG`: 5

## Review Buckets

- `REVIEW_MOVE_COPY`: 110
- `REVIEW_MOVE_COUPLED_RULES`: 36
- `REVIEW_MOVE_ENGINE`: 35

## Replace Highlights

- `locales/ca/move-trigger.json`: REPLACE_MOVE_TEXT - Localized move-trigger strings include move-specific text and should be rewritten with the new move catalog
- `locales/ca/move.json`: REPLACE_MOVE_TEXT - Localized move names and move effect text must be rewritten for a new commercial move catalog
- `locales/da/move.json`: REPLACE_MOVE_TEXT - Localized move names and move effect text must be rewritten for a new commercial move catalog
- `locales/de/move-trigger.json`: REPLACE_MOVE_TEXT - Localized move-trigger strings include move-specific text and should be rewritten with the new move catalog
- `locales/de/move.json`: REPLACE_MOVE_TEXT - Localized move names and move effect text must be rewritten for a new commercial move catalog
- `locales/en/move-trigger.json`: REPLACE_MOVE_TEXT - Localized move-trigger strings include move-specific text and should be rewritten with the new move catalog
- `locales/en/move.json`: REPLACE_MOVE_TEXT - Localized move names and move effect text must be rewritten for a new commercial move catalog
- `locales/es-419/move-trigger.json`: REPLACE_MOVE_TEXT - Localized move-trigger strings include move-specific text and should be rewritten with the new move catalog
- `locales/es-419/move.json`: REPLACE_MOVE_TEXT - Localized move names and move effect text must be rewritten for a new commercial move catalog
- `locales/es-ES/move-trigger.json`: REPLACE_MOVE_TEXT - Localized move-trigger strings include move-specific text and should be rewritten with the new move catalog
- `locales/es-ES/move.json`: REPLACE_MOVE_TEXT - Localized move names and move effect text must be rewritten for a new commercial move catalog
- `locales/fr/move-trigger.json`: REPLACE_MOVE_TEXT - Localized move-trigger strings include move-specific text and should be rewritten with the new move catalog
- `locales/fr/move.json`: REPLACE_MOVE_TEXT - Localized move names and move effect text must be rewritten for a new commercial move catalog
- `locales/he/move.json`: REPLACE_MOVE_TEXT - Localized move names and move effect text must be rewritten for a new commercial move catalog
- `locales/hi/move.json`: REPLACE_MOVE_TEXT - Localized move names and move effect text must be rewritten for a new commercial move catalog
- `locales/id/move.json`: REPLACE_MOVE_TEXT - Localized move names and move effect text must be rewritten for a new commercial move catalog
- `locales/it/move-trigger.json`: REPLACE_MOVE_TEXT - Localized move-trigger strings include move-specific text and should be rewritten with the new move catalog
- `locales/it/move.json`: REPLACE_MOVE_TEXT - Localized move names and move effect text must be rewritten for a new commercial move catalog
- `locales/ja/move-trigger.json`: REPLACE_MOVE_TEXT - Localized move-trigger strings include move-specific text and should be rewritten with the new move catalog
- `locales/ja/move.json`: REPLACE_MOVE_TEXT - Localized move names and move effect text must be rewritten for a new commercial move catalog

## Review Highlights

- `locales/ca/ability-trigger.json`: REVIEW_MOVE_COPY - Non-move locale files with move-related references should be checked after move/catalog rewrite
- `locales/ca/battle.json`: REVIEW_MOVE_COPY - Non-move locale files with move-related references should be checked after move/catalog rewrite
- `locales/ca/egg.json`: REVIEW_MOVE_COPY - Non-move locale files with move-related references should be checked after move/catalog rewrite
- `locales/da/ability-trigger.json`: REVIEW_MOVE_COPY - Non-move locale files with move-related references should be checked after move/catalog rewrite
- `locales/da/egg.json`: REVIEW_MOVE_COPY - Non-move locale files with move-related references should be checked after move/catalog rewrite
- `locales/de/ability-trigger.json`: REVIEW_MOVE_COPY - Non-move locale files with move-related references should be checked after move/catalog rewrite
- `locales/de/arena-tag.json`: REVIEW_MOVE_COPY - Non-move locale files with move-related references should be checked after move/catalog rewrite
- `locales/de/battle.json`: REVIEW_MOVE_COPY - Non-move locale files with move-related references should be checked after move/catalog rewrite
- `locales/de/battler-tags.json`: REVIEW_MOVE_COPY - Non-move locale files with move-related references should be checked after move/catalog rewrite
- `locales/de/egg.json`: REVIEW_MOVE_COPY - Non-move locale files with move-related references should be checked after move/catalog rewrite
- `locales/de/modifier-type.json`: REVIEW_MOVE_COPY - Non-move locale files with move-related references should be checked after move/catalog rewrite
- `locales/de/status-effect.json`: REVIEW_MOVE_COPY - Non-move locale files with move-related references should be checked after move/catalog rewrite
- `locales/en/ability-trigger.json`: REVIEW_MOVE_COPY - Non-move locale files with move-related references should be checked after move/catalog rewrite
- `locales/en/arena-tag.json`: REVIEW_MOVE_COPY - Non-move locale files with move-related references should be checked after move/catalog rewrite
- `locales/en/battle.json`: REVIEW_MOVE_COPY - Non-move locale files with move-related references should be checked after move/catalog rewrite
- `locales/en/battler-tags.json`: REVIEW_MOVE_COPY - Non-move locale files with move-related references should be checked after move/catalog rewrite
- `locales/en/egg.json`: REVIEW_MOVE_COPY - Non-move locale files with move-related references should be checked after move/catalog rewrite
- `locales/en/modifier-type.json`: REVIEW_MOVE_COPY - Non-move locale files with move-related references should be checked after move/catalog rewrite
- `locales/en/status-effect.json`: REVIEW_MOVE_COPY - Non-move locale files with move-related references should be checked after move/catalog rewrite
- `locales/es-419/ability-trigger.json`: REVIEW_MOVE_COPY - Non-move locale files with move-related references should be checked after move/catalog rewrite

## Directory Concentration

- Replace `src/data/balance/moves`: 5 files
- Replace `locales/ca/move-trigger.json`: 1 files
- Replace `locales/ca/move.json`: 1 files
- Replace `locales/da/move.json`: 1 files
- Replace `locales/de/move-trigger.json`: 1 files
- Replace `locales/de/move.json`: 1 files
- Replace `locales/en/move-trigger.json`: 1 files
- Replace `locales/en/move.json`: 1 files
- Replace `locales/es-419/move-trigger.json`: 1 files
- Replace `locales/es-419/move.json`: 1 files
- Replace `locales/es-ES/move-trigger.json`: 1 files
- Replace `locales/es-ES/move.json`: 1 files
- Review `src/data/mystery-encounters/encounters`: 14 files
- Review `src/data/mystery-encounters/requirements`: 2 files
- Review `src/system/version-migration/versions`: 2 files
- Review `locales/ca/ability-trigger.json`: 1 files
- Review `locales/ca/battle.json`: 1 files
- Review `locales/ca/egg.json`: 1 files
- Review `locales/da/ability-trigger.json`: 1 files
- Review `locales/da/egg.json`: 1 files
- Review `locales/de/ability-trigger.json`: 1 files
- Review `locales/de/arena-tag.json`: 1 files
- Review `locales/de/battle.json`: 1 files
- Review `locales/de/battler-tags.json`: 1 files

## Notes

- `src/data/moves/move.ts` is the highest-friction file because it mixes reusable engine classes with Pokemon move definitions and move-specific effect code.
- Learnsets are spread across level-up moves, egg moves, signature moves, TMs, move-based evolutions, and move-based form changes.
- Locale rewrites are not limited to `move.json`; other battle copy files may need cleanup after the new move catalog is in place, but this sweep only marks `move.json` and `move-trigger.json` as replace-now.
- This sweep intentionally treats generic move engine files as review, not delete, because they can often survive a content rewrite with targeted remapping.

## Output Files

- `COMMERCIAL_MOVE_CONTENT_REPLACE_MANIFEST.tsv`
- `COMMERCIAL_MOVE_ENGINE_REVIEW.tsv`

## Key Sources

- `src/enums/move-id.ts`
- `src/data/moves/move.ts`
- `src/data/balance/pokemon-level-moves.ts`
- `src/data/balance/moves/egg-moves.ts`
- `src/data/balance/moves/signature-moves.ts`
- `src/data/balance/tms.ts`
- `src/data/balance/tm-species-map.ts`
- `src/data/pokemon-forms.ts`
- `src/data/battle-anims.ts`
- `locales/*/move.json`
- `locales/*/move-trigger.json`

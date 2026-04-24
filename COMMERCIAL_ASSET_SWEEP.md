# Commercial Asset Sweep

Generated: 2026-04-05

This sweep covers runtime assets under `assets/` and ignores repo metadata such as `.git`, `.github`, `LICENSES/`, and `REUSE.toml`.

## Bottom Line

- Total runtime asset files scanned: 32,684
- Assets that should be replaced before a commercial release: 32,524
- Assets that may stay only with AGPL acceptance or manual review: 160

## Replace Buckets

- `REPLACE_LICENSE_BLOCKER`: 22,656
- `REPLACE_POKEMON_GAME_ASSET`: 9,868

## License Breakdown For Replace Set

- `UNLICENSED`: 19,635
- `AGPL-3.0-only`: 9,868
- `LicenseRef-FAIR-USE`: 1,530
- `LicenseRef-POKEMON-REBORN`: 1,163
- `CC-BY-NC-SA-4.0`: 323
- `LicenseRef-NO-REUSE`: 5

## Highest-Risk Directories

- `audio/`: 2,732 files (LicenseRef-FAIR-USE=1,526, LicenseRef-POKEMON-REBORN=1,163, CC-BY-NC-SA-4.0=28, UNLICENSED=11, CC0-1.0=4)
- `battle-anims/`: 923 files (AGPL-3.0-only=874, CC-BY-NC-SA-4.0=49)
- `images/pokemon/`: 24,990 files (UNLICENSED=16,116, AGPL-3.0-only=8,634, CC-BY-NC-SA-4.0=240)
- `images/trainer/`: 614 files (UNLICENSED=308, AGPL-3.0-only=302, CC-BY-NC-SA-4.0=4)
- `images/items/`: 529 files (UNLICENSED=501, AGPL-3.0-only=26, CC-BY-NC-SA-4.0=2)
- `images/ui/`: 1,561 files (UNLICENSED=1,475, AGPL-3.0-only=86)
- `images/arenas/`: 189 files (UNLICENSED=185, AGPL-3.0-only=4)
- `images/mogger-mon/`: 71 files (UNLICENSED=71)
- `images/mystery-encounters/`: 44 files (UNLICENSED=23, AGPL-3.0-only=21)
- `images/egg/`: 26 files (UNLICENSED=17, AGPL-3.0-only=9)
- `images/events/`: 150 files (UNLICENSED=150)
- `images/pokeball/`: 18 files (UNLICENSED=18)
- `fonts/`: 8 files (UNLICENSED=8)

## Notes

- Every file under `audio/` is already a commercial blocker by license or missing-license status.
- Most of `images/pokemon/` is either unlicensed or AGPL; even the AGPL portion should be replaced for a clean non-Pokemon commercial product.
- `battle-anims/` is mostly AGPL, but the files are Pokemon move animation definitions; treat them as replace-now for a commercial reskin.
- `images/ui/`, `images/arenas/`, `images/effects/`, `images/inputs/`, and `images/cg/` contain a mix of unlicensed and AGPL material. Unlicensed files are in the replace manifest; the remaining AGPL files need manual review before reuse.
- The remaining keep/review set is intentionally small and should not be treated as legally cleared beyond the repo metadata scan.

## Output Files

- `COMMERCIAL_ASSET_REPLACE_MANIFEST.tsv`: exact path-by-path replacement manifest
- `COMMERCIAL_ASSET_KEEP_REVIEW.tsv`: files not auto-marked for replacement, mostly AGPL or CC0 and still requiring product review

## Sources Used

- `assets/REUSE.toml`
- `assets/audio/REUSE.toml`
- `assets/battle-anims/REUSE.toml`
- `assets/images/REUSE.toml`
- `assets/images/pokemon/variant/REUSE.toml`
- `assets/LICENSES/LicenseRef-FAIR-USE.txt`
- `assets/LICENSES/LicenseRef-NO-REUSE.txt`
- `assets/LICENSES/LicenseRef-POKEMON-REBORN.txt`

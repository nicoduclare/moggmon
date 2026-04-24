<!--
SPDX-FileCopyrightText: 2024-2025 Pagefault Games

SPDX-License-Identifier: CC-BY-NC-SA-4.0
-->

# Mogger Mon

Mogger Mon is a browser-based creature battler with a roguelite run structure, local-first boot flow, and a custom generated roster layered on top of a large inherited battle engine.

This repo currently contains:

- the playable Mogger Mon client
- Mogger Mon-specific UI, copy, branding, and launch flow changes
- tooling for generated roster installs, icons, TCG-style source cards, and redraw prep
- a clean non-mon art redraw pack at [output/original-art-redo-pack](./output/original-art-redo-pack)

## Quick Start

```bash
pnpm install
pnpm start:dev
```

The checked-in env presets are local-first and default to guest play. Use [.env.example](./.env.example) as the baseline for any new environment file. `VITE_AURA_LOGIN_ORIGIN` and `VITE_AURA_CLIENT_ID` configure the optional Login with Aura path.

Useful commands:

- `pnpm typecheck`
- `pnpm build`
- `pnpm preview`
- `pnpm pixelify:asset -- --input <in.png> --output <out.png>`

## Project Layout

- `src`: game code and debug labs
- `scripts`: asset and content pipeline scripts
- `assets`: game assets submodule
- `locales`: localization submodule
- `docs`: launch notes, manifests, and planning docs

## Open Source Status

The codebase is much closer to Mogger Mon branding now, but it is not yet a clean public OSS drop.

Before publishing, review:

- [open-source-readiness.md](./docs/open-source-readiness.md)
- [mogger-mon-item-taxonomy.md](./docs/mogger-mon-item-taxonomy.md)
- [generation-prompts.md](./docs/generation-prompts.md)
- [COMMERCIAL_ASSET_SWEEP.md](./COMMERCIAL_ASSET_SWEEP.md)
- [COMMERCIAL_ASSET_REPLACE_MANIFEST.tsv](./COMMERCIAL_ASSET_REPLACE_MANIFEST.tsv)
- [COMMERCIAL_MOVE_CONTENT_SWEEP.md](./COMMERCIAL_MOVE_CONTENT_SWEEP.md)

The main remaining issues are asset provenance, inherited docs/credits content, and cleanup of legacy storage paths inside the asset tree.

## Licensing

This repository seeks to be [REUSE compliant](https://reuse.software/): copyright and/or licensing information for each file is stored either in the file itself or in an associated `REUSE.toml` file.

An abbreviated summary is:

- Source code is licensed under [AGPL-v3.0-only](LICENSES/AGPL-3.0-only.txt), unless otherwise noted.
- Documentation is licensed under [CC-BY-NC-SA-4.0](LICENSES/CC-BY-NC-SA-4.0.txt), unless otherwise noted.
- Auto-generated files and files of insignificant originality are licensed under [CC0-1.0](LICENSES/CC0-1.0.txt), unless otherwise noted.
- Assets are mixed-provenance and must be reviewed file-by-file. Some files in `assets/` still have no reusable license declaration.

# Contributing to Mogger Mon

Mogger Mon is a Phaser/TypeScript creature battler with a local-first dev setup, custom Mogger Mon content, and a retained battle engine that is still being cleaned up for public release.

## Setup

1. Install Node `>=24.9.0` and `pnpm` 10.x.
2. Run `pnpm install`.
3. Run `pnpm start:dev`.
4. Open the local URL printed by Vite.

The checked-in env files default to guest play. Aura login is optional and configured with `VITE_AURA_LOGIN_ORIGIN` and `VITE_AURA_CLIENT_ID`.

## Useful Commands

- `pnpm typecheck`
- `pnpm build`
- `pnpm exec ls-lint`
- `pnpm exec biome check --write --staged --no-errors-on-unmatched --diagnostic-level=error`

## Development Notes

- Keep user-facing copy in Mogger Mon language: Mogger Mon, Mogmaster, Maxx, Cryotank, BrainDance, Zaza, relic, archive, and technique.
- Internal engine names may still use inherited names while the migration is in progress. Do not rename public APIs, save schema, or enum IDs casually.
- Treat generated art prompts, reference caches, and raw source packs as private artifacts unless they have been rewritten for public use.
- Put reusable launch notes in `docs/`; keep scratch output under ignored `output/private-generation-prompts/`.
- Use the dev labs for asset validation: title query params support Sprite Lab, Battle Lab, Move Lab, Maxx Lab, and Archive Lab.

## Testing

For gameplay changes, prefer a manual in-browser check plus the narrowest automated or static check that covers the change. UI-only patches usually need a real browser pass; data or battle-logic patches should include a focused test when practical.

## Pull Requests

Use conventional commit-style titles when possible, for example:

```text
fix(battle): reset cryotank tray between lab swaps
docs(launch): clean public contributor guide
```

Before opening a PR, run the relevant checks and call out anything not tested.

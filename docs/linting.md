# Linting

Mogger Mon uses Biome for source formatting/linting and `ls-lint` for repository naming hygiene.

Useful commands:

```bash
pnpm biome:all
pnpm exec ls-lint
pnpm typecheck
pnpm build
```

Generated scratch artifacts should stay under ignored output folders. If a generated folder must be committed, prefer kebab-case paths or add a deliberate ignore rule with a short explanation.

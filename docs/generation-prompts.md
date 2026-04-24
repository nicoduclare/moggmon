# Generation Prompt Storage

The historical sprite and card prompt JSON is no longer kept in public docs because it contains source-reference language that is useful for local regeneration but not appropriate for an open-source launch package.

Local tools now look for the private prompt file at:

```text
output/private-generation-prompts/mogger-mon-prompts.json
```

The private TCG/source-reference cache lives beside it:

```text
output/private-generation-prompts/mogger-mon-tcg
output/private-generation-prompts/brainrot-wiki
```

You can override that path with:

```bash
MOGGER_MON_PROMPTS_FILE=/absolute/path/to/prompts.json
```

Public art docs should describe final Mogger Mon art direction and asset requirements, not private prompt history or source-reference scaffolding.

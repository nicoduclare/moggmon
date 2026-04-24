# Rotmon TCG Source Assets

This folder is the tracked source package for regenerating the final TCG card renders. The local generated source folders may live either in `tcg/raw` or in the ignored workspace at `output/private-generation-prompts/mogger-mon-tcg`; the render and sync helpers prefer `tcg/raw` only when it contains numeric card folders.

- `raw/NNN/full-art-2.jpg` or `output/private-generation-prompts/mogger-mon-tcg/NNN/full-art-2.jpg` is the current source art for card `NNN`.
- `raw/NNN/prompt-2.txt` / `meta-2.json` are the generation prompt and metadata for the current source art.
- `raw/NNN/reference-style.jpg` and `raw/NNN/reference.*` are the visual references used while generating the art.
- `raw/NNN/holo-mask-2.png` is the current generated holo mask for the art.
- `borders/` contains the rarity frames and card alpha mask.
- `icons/` contains the type icons plus shared TCG UI icons.
- `prompts/` and `dex/` contain the text data used by `scripts/render_mogmon_tcg_cards.py`.
- `evolution-paths.tsv` is the human-editable card evolution path. Edit `evolvesFromCard` there when a TCG card should belong to a different family chain.
- `final-reference/` keeps the manifest and preview grid from the final grouped render.

Render grouped final cards:

```sh
python3 scripts/render_mogmon_tcg_cards.py \
  --border-dir tcg/borders \
  --icon-dir tcg/icons \
  --art-name full-art-2 \
  --out-dir output/private-generation-prompts/mogger-mon-tcg/cards/final \
  --group-by-rarity
```

Sync final cards into the shipped asset layout:

```sh
python3 scripts/sync_tcg_final_assets.py
```

Sync one edited card after rerendering it:

```sh
swift scripts/generate_tcg_holo_masks.swift --source-dir output/private-generation-prompts/mogger-mon-tcg --art-name full-art-2 --dex 3 --overwrite
python3 scripts/render_mogmon_tcg_cards.py --dex 3 --out-dir output/private-generation-prompts/mogger-mon-tcg/cards/final
python3 scripts/sync_tcg_final_assets.py --dex 3
```

The shipped flattened cards live in `assets/tcg/final`. Each card is available both as `assets/tcg/final/NNN.png` and as `assets/tcg/final/NNN/card.png` with its matching `assets/tcg/final/NNN/mask.png`.

When editing `evolution-paths.tsv`:

- `card` is the visible TCG card number, such as `003`.
- `sourceDex` is the source art folder under the raw source directory; for most cards it matches `card`, but a few cards may use alternate source folders like `237`, `478`, or `571`.
- `evolvesFromCard` is the visible previous card number. Leave it blank for a base or solo card.
- Family grouping is inferred automatically by walking `evolvesFromCard` back to the root card, so branches only need to point at their parent.
- `stageLabel` controls the card stage text and rarity logic. Common values are `base`, `mid`, `final`, `branch-final`, and `solo`.

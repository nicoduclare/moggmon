# Mogger Mon Token/NFT Gameplay Pass

## Direction

Use crypto as optional progression proof, cosmetics, and social collection. Do not sell battle power, do not interrupt runs with wallet prompts, and do not require a wallet for the core game loop.

The current codebase already has the important entry point: `src/tempaitown-host.ts` can discover the embedded TempaiTown auth/wallet state and namespace saves by wallet/profile. Keep chain operations in the parent host and expose small game RPCs to the Phaser app.

## Best First Loop: MogPass Missions

Add daily and weekly contracts that reward off-chain points first, with optional claim/mint later.

- Win a run with a weird starter trait combo.
- Clear a biome without using revives.
- Hatch a generated roster egg.
- Beat a rival/boss with a low-cost starter.
- Complete a rotating "meme rule" challenge, such as no repeats, only food traits, or only cryo-caught recruits.

Rewards should be "Mog Dust", "Cryo Shards", or "MogPass XP". These can later be claimable as token-backed balances, but gameplay should treat them as normal reward currency.

## NFT Use That Adds Fun

Mint run receipts and collectibles, not power.

- **Run Badge NFTs:** soulbound or low-friction collectible receipt after a clear, streak, rare hatch, or personal best. Metadata includes seed, mode, wave, starter lineup, notable trait tags, and a generated card image.
- **TCG Card Mints:** use the existing TCG render pipeline to mint a cosmetic card for a favorite Mogger Mon. This is a showcase/social loop, not a stat source.
- **Starter Skin Ownership:** NFTs unlock alternate palettes, title-screen badges, card frames, or starter-select flair.
- **Season Trophy:** end-of-season badges for leaderboard brackets, daily participation, and challenge clears.

## Avoid

- Pay-to-win stat boosts.
- Real-money gacha for eggs, vouchers, or unlockable traits.
- Token staking/deposits inside battle flow.
- Blocking save/load or starter access behind wallet state.
- On-chain writes during fast UI interactions.

## Implementation Phases

1. **Host RPC Contract**
   - Add game-to-parent methods: `inventory.get`, `rewards.preview`, `rewards.claim`, `nft.mintRunBadge`, `market.open`.
   - The game sends signed/structured run summaries; the parent verifies and handles chain calls.

2. **Reward Events**
   - Emit local reward candidates from existing achievement, voucher, egg, run-history, and clear paths.
   - Keep rewards pending until the run ends or returns to menu.

3. **Claim UI**
   - Add a post-run reward panel showing off-chain points, badge eligibility, and optional mint/claim buttons.
   - Include a disabled/offline state for non-embedded or non-wallet sessions.

4. **Cosmetic Inventory**
   - Load owned skins/badges from `inventory.get`.
   - Apply only to starter select, title/profile surfaces, TCG card frames, and optional party markers.

5. **Season Layer**
   - Add rotating contracts and season badges.
   - Use wallet/profile identity only for attribution and optional claims.

## Asset Needs

- Small token/currency icons: Mog Dust, Cryo Shard, Run Badge, Season XP.
- Claim/reward panel UI chrome matching the left-rail starter style.
- Badge frame set: common, rare, epic, legendary, event.
- Cosmetic cryotank overlays and party slot markers.
- TCG card export templates for minted run badges.

## Suggested First Ship Slice

Ship a non-chain version first: post-run MogPass missions, local/off-chain points, and visible badge eligibility. Then wire the same reward objects to TempaiTown host RPC for claim/mint. This makes the feature fun before the wallet integration exists and keeps chain risk out of the battle loop.

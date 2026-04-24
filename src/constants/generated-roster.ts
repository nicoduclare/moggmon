import type { SpeciesId } from "#enums/species-id";

// Single source of truth for the playable/generated Mogger Mon roster.
// Dex 201 only has letter-form assets installed, so keep it out of random pools
// until the base runtime atlas/icon path is normalized.
export const GENERATED_ROSTER_MAX_DEX = 206;

export const GENERATED_ROSTER_DEXES = Array.from(
  { length: GENERATED_ROSTER_MAX_DEX },
  (_, index) => (index + 1) as SpeciesId,
).filter(dex => dex !== 201);

const GENERATED_ROSTER_DEX_SET = new Set<number>(GENERATED_ROSTER_DEXES);

export function isGeneratedRosterSpeciesId(speciesId: number): speciesId is SpeciesId {
  return GENERATED_ROSTER_DEX_SET.has(speciesId);
}

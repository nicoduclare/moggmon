import { speciesStarterCosts } from "#balance/starters";
import { GENERATED_ROSTER_DEXES } from "#constants/generated-roster";
import type { SpeciesId } from "#enums/species-id";

// Starter-eligible Mogger Mon species within the generated roster, in dex order.
export const GENERATED_STARTER_POOL = GENERATED_ROSTER_DEXES.filter(dex =>
  Object.hasOwn(speciesStarterCosts, dex),
) as SpeciesId[];

// Default number of generated starters unlocked for a fresh save.
export const DEFAULT_GENERATED_STARTER_COUNT = Math.min(18, GENERATED_STARTER_POOL.length);

export function getGeneratedStarterSpecies(limit = DEFAULT_GENERATED_STARTER_COUNT): SpeciesId[] {
  const clampedLimit = Math.max(0, Math.min(limit, GENERATED_STARTER_POOL.length));
  return GENERATED_STARTER_POOL.slice(0, clampedLimit);
}

export const GENERATED_STARTER_SPECIES = getGeneratedStarterSpecies();

export const GENERATED_STARTER_SPECIES_SET = new Set<SpeciesId>(GENERATED_STARTER_SPECIES);

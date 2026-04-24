import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const LOCALES_DIR = path.join(ROOT, "locales");
const ENGLISH_POKEMON_FILE = path.join(LOCALES_DIR, "en", "pokemon.json");
const SPECIES_SOURCE_FILE = path.join(ROOT, "src", "data", "balance", "pokemon-species.ts");
const EVOLUTIONS_SOURCE_FILE = path.join(ROOT, "src", "data", "balance", "pokemon-evolutions.ts");
const MEGALIST_FILE = path.join(ROOT, "scripts", "data", "brainrot-trait-megalist.json");

const REGION_PREFIXES = ["alola", "galar", "hisui", "paldea", "bloodmoon", "eternal"];
const REGION_TOKENS = {
  alola: ["tazza", "tropi"],
  galar: ["bici", "cromo"],
  hisui: ["stone", "sahur"],
  paldea: ["pata", "fiesta"],
  bloodmoon: ["luna", "sahur"],
  eternal: ["aura", "eterna"],
};
const FAMILY_ROOT_OVERRIDES = {
  bulbasaur: {
    rootString: "patapim sprout",
    baseWords: ["patapim"],
    stageTokens: ["sprout", "grove", "ancient", "omega"],
  },
  charmander: {
    rootString: "tung tung sahur",
    baseWords: ["tung", "sahur"],
    stageTokens: ["", "rizz", "bomba", "omega"],
  },
  squirtle: {
    rootString: "trelalala",
    baseWords: ["trelalala"],
    stageTokens: ["", "marini", "camelo", "bomba"],
  },
};
const STAGE_TOKENS = [[""], ["max", "plus", "prime"], ["ultra", "omega", "boss"], ["omega", "final", "boss"]];
const COLLISION_TOKENS = ["tazza", "bici", "luna", "boss", "boo", "brr"];
const FALLBACK_COLLISION_TOKENS = ["nova", "zaza", "giga", "mimi", "loco", "tiki", "fufu", "kiki"];
const BAD_ATOMS = new Set([
  "admin",
  "blog",
  "brainrot",
  "brainrots",
  "file",
  "job",
  "list",
  "png",
  "template",
  "trader",
  "user",
  "webp",
  "wiki",
]);
const TRAIT_PREFERENCES = {
  water: ["trelalala", "camelo", "frigo", "dolphi", "moby", "octo", "aquana", "fishi"],
  fire: ["sahur", "rizz", "bomba", "croco"],
  electric: ["brr", "patapim", "bici", "teh"],
  plant: ["corni", "pipi", "avoca", "bambu", "berry", "cacto", "melon"],
  reptile: ["sahur", "tung", "croco", "drago", "hydra"],
  mammal: ["pipi", "camelo", "gatti", "bau", "bunny", "panda", "goat", "bear"],
  bird: ["voli", "pegasi", "cielo"],
  bug: ["spidi", "octo", "bluebe", "chimpa"],
  food: ["cappu", "boba", "avoca", "taco", "berry", "melon", "banana", "sweeti"],
  spooky: ["boo", "ombra", "skull"],
  psychic: ["braini", "telepi", "telemo"],
  metal: ["techi", "dinoss", "vicios"],
  cosmic: ["cosmi", "luna", "pegasi"],
  fight: ["assa", "boss", "band", "bici"],
  cute: ["bunny", "eggi", "panda", "loli", "pepper"],
  music: ["baller", "boppin", "lololo"],
  speed: ["jetsk", "spin", "zoom"],
  wild: ["tung", "tralala", "camelo", "bunny", "pipi"],
};
const TYPE_TRAITS = {
  NORMAL: ["wild"],
  FIRE: ["fire"],
  WATER: ["water"],
  ELECTRIC: ["electric"],
  GRASS: ["plant"],
  GROUND: ["mammal"],
  ROCK: ["reptile", "metal"],
  STEEL: ["metal"],
  ICE: ["water", "cosmic"],
  FLYING: ["bird"],
  BUG: ["bug"],
  POISON: ["spooky"],
  GHOST: ["spooky"],
  DARK: ["spooky", "fight"],
  PSYCHIC: ["psychic"],
  DRAGON: ["reptile"],
  FIGHTING: ["fight"],
  FAIRY: ["cute", "food"],
};
const CATEGORY_TRAITS = {
  seed: ["plant"],
  weed: ["plant"],
  leaf: ["plant"],
  herb: ["plant"],
  flower: ["plant"],
  mushroom: ["plant", "food"],
  cottonweed: ["plant"],
  lizard: ["reptile"],
  flame: ["fire"],
  dragon: ["reptile"],
  volcano: ["fire"],
  turtle: ["water"],
  shellfish: ["water"],
  fish: ["water"],
  goldfish: ["water"],
  aqua: ["water"],
  bubble: ["water"],
  jellyfish: ["water"],
  coral: ["water"],
  angler: ["water"],
  mouse: ["mammal"],
  mole: ["mammal"],
  raccoon: ["mammal"],
  cat: ["mammal"],
  fox: ["mammal"],
  puppy: ["mammal"],
  pig: ["mammal", "food"],
  monkey: ["mammal"],
  bird: ["bird"],
  owl: ["bird"],
  beak: ["bird"],
  duck: ["bird", "water"],
  bat: ["bird", "spooky"],
  bee: ["bug"],
  insect: ["bug"],
  moth: ["bug"],
  worm: ["bug"],
  cocoon: ["bug"],
  butterfly: ["bug"],
  mantis: ["bug"],
  crab: ["water"],
  horse: ["mammal"],
  bull: ["mammal"],
  stag: ["mammal"],
  frog: ["water"],
  tadpole: ["water"],
  star: ["cosmic"],
  magnet: ["metal"],
  legendary: ["cosmic", "fight"],
  genetic: ["psychic"],
  virtual: ["metal", "psychic"],
  fossil: ["reptile", "cosmic"],
  human: ["fight"],
  sleeping: ["cute"],
  happiness: ["cute"],
  darkness: ["spooky"],
  moonlight: ["cosmic"],
  sun: ["fire", "cosmic"],
  light: ["electric"],
  freeze: ["water", "cosmic"],
  soft: ["cute"],
  tissue: ["spooky"],
  spirit: ["spooky"],
  arrow: ["fight"],
  quill: ["bird"],
  spike: ["fight"],
  pin: ["fight"],
  trap: ["fight"],
  illusion: ["psychic"],
  tricky: ["psychic"],
  evolution: ["wild"],
  imitation: ["psychic"],
  psi: ["psychic"],
  superpower: ["fight"],
  valiant: ["fight"],
  barrier: ["metal"],
  megaton: ["fight"],
  long: ["wild"],
  body: ["wild"],
  scout: ["speed"],
};
const CATEGORY_ATOM_OVERRIDES = {
  seed: ["corni"],
  weed: ["corni"],
  leaf: ["corni"],
  herb: ["corni"],
  flower: ["corni"],
  cottonweed: ["corni"],
  lizard: ["sahur"],
  dragon: ["sahur"],
  flame: ["rizz"],
  volcano: ["rizz"],
  turtle: ["trelalala"],
  shellfish: ["trelalala"],
  fish: ["trelalala"],
  goldfish: ["trelalala"],
  aqua: ["trelalala"],
  bubble: ["trelalala"],
  jellyfish: ["trelalala"],
  coral: ["trelalala"],
  angler: ["trelalala"],
  mouse: ["pipi"],
  mole: ["pipi"],
  raccoon: ["pipi"],
  cat: ["gatti"],
  fox: ["bau"],
  puppy: ["bau"],
  monkey: ["bunny"],
  bird: ["voli"],
  owl: ["voli"],
  beak: ["voli"],
  duck: ["voli"],
  bat: ["boo"],
  bee: ["brr"],
  insect: ["spidi"],
  moth: ["spidi"],
  worm: ["spidi"],
  cocoon: ["spidi"],
  butterfly: ["spidi"],
  mantis: ["spidi"],
  frog: ["trelalala"],
  tadpole: ["trelalala"],
  star: ["cosmi"],
  magnet: ["techi"],
  legendary: ["boss"],
  genetic: ["braini"],
  virtual: ["techi"],
  fossil: ["croco"],
  sleeping: ["bunny"],
  darkness: ["ombra"],
  moonlight: ["luna"],
  sun: ["rizz"],
  freeze: ["frigo"],
  spirit: ["boo"],
  evolution: ["tralala"],
};
const CATEGORY_SKIP_WORDS = new Set([
  "big",
  "double",
  "electric",
  "fairy",
  "fighting",
  "fire",
  "flying",
  "ghost",
  "grass",
  "ground",
  "ice",
  "new",
  "normal",
  "poison",
  "pokemon",
  "psychic",
  "rock",
  "mogmon",
  "shape",
  "single",
  "species",
  "steel",
  "tiny",
  "triple",
  "water",
  "wild",
]);
const SAMPLE_KEYS = [
  "bulbasaur",
  "ivysaur",
  "venusaur",
  "charmander",
  "charmeleon",
  "charizard",
  "squirtle",
  "wartortle",
  "blastoise",
  "pichu",
  "pikachu",
  "raichu",
  "alolaRaichu",
  "eevee",
  "vaporeon",
  "jolteon",
  "flareon",
];

function unique(values) {
  return [...new Set(values)];
}

function hashString(value) {
  let hash = 0;
  for (const char of value) {
    hash = (hash * 31 + char.charCodeAt(0)) | 0;
  }
  return Math.abs(hash);
}

function pick(list, salt) {
  return list[hashString(salt) % list.length];
}

function localeKeyToEnumKey(localeKey) {
  return localeKey.replace(/([a-z0-9])([A-Z])/g, "$1_$2").toUpperCase();
}

function getRegionPrefix(localeKey) {
  return REGION_PREFIXES.find(prefix => localeKey.startsWith(prefix)) ?? null;
}

function normalizeCategoryWords(category) {
  return category
    .replace(/\s+(Pokémon|Mogger Mon)$/i, "")
    .toLowerCase()
    .split(/[\s-]+/)
    .filter(Boolean)
    .filter(word => !CATEGORY_SKIP_WORDS.has(word));
}

function sanitizeAtoms(atoms, atomSet) {
  return unique(
    atoms.filter(
      atom =>
        atomSet.has(atom) && atom.length >= 3 && atom.length <= 10 && /^[a-z]+$/.test(atom) && !BAD_ATOMS.has(atom),
    ),
  );
}

function buildAtomPools(megalist) {
  const atomSet = new Set(
    megalist.allAtoms.filter(atom => atom.length >= 3 && atom.length <= 10 && /^[a-z0-9]+$/.test(atom)),
  );
  const traitPools = {};

  for (const trait of unique([...Object.keys(megalist.atomsByTrait), ...Object.keys(TRAIT_PREFERENCES)])) {
    const preferred = sanitizeAtoms(TRAIT_PREFERENCES[trait] ?? [], atomSet);
    const fallback = sanitizeAtoms(megalist.atomsByTrait[trait] ?? [], atomSet);
    traitPools[trait] = preferred.length > 0 ? preferred : fallback;
  }

  return { atomSet, traitPools };
}

function pickTraitAtom(atomPools, traits, salt, used = []) {
  const candidates = unique(traits.flatMap(trait => atomPools.traitPools[trait] ?? [])).filter(
    atom => !used.includes(atom),
  );
  return candidates.length > 0 ? pick(candidates, salt) : null;
}

function pickCategoryAtom(category, atomPools, salt, used = []) {
  const words = normalizeCategoryWords(category);

  for (const word of words) {
    const direct = sanitizeAtoms(CATEGORY_ATOM_OVERRIDES[word] ?? [], atomPools.atomSet).filter(
      atom => !used.includes(atom),
    );
    if (direct.length > 0) {
      return pick(direct, `${salt}:override:${word}`);
    }
  }

  const traits = unique(words.flatMap(word => CATEGORY_TRAITS[word] ?? []));
  return traits.length > 0 ? pickTraitAtom(atomPools, traits, `${salt}:category`, used) : null;
}

function pickTypeAtom(type, atomPools, salt, used = []) {
  return pickTraitAtom(atomPools, TYPE_TRAITS[type] ?? ["wild"], `${salt}:type:${type}`, used);
}

function parseSpeciesMetadata(source) {
  const pattern =
    /new PokemonSpecies\(SpeciesId\.([A-Z0-9_]+),\s*\d+,\s*(?:true|false),\s*(?:true|false),\s*(?:true|false),\s*"([^"]+)",\s*PokemonType\.([A-Z_]+|null)(?:,\s*(?:PokemonType\.([A-Z_]+)|null))?/g;
  return new Map(
    [...source.matchAll(pattern)].map(([, enumKey, category, primaryType, secondaryType]) => [
      enumKey,
      {
        category,
        primaryType: primaryType === "null" ? "NORMAL" : primaryType,
        secondaryType: secondaryType ?? null,
      },
    ]),
  );
}

function parseEvolutionGraph(source) {
  const childrenBySource = new Map();
  let currentSource = null;

  for (const line of source.split(/\r?\n/)) {
    const sourceMatch = line.match(/^\s*\[SpeciesId\.([A-Z0-9_]+)\]: \[$/);
    if (sourceMatch) {
      currentSource = sourceMatch[1];
      if (!childrenBySource.has(currentSource)) {
        childrenBySource.set(currentSource, []);
      }
      continue;
    }

    if (!currentSource) {
      continue;
    }

    const targetMatch = line.match(/new Species(?:Form)?Evolution\(SpeciesId\.([A-Z0-9_]+)/);
    if (targetMatch) {
      const targets = childrenBySource.get(currentSource);
      if (!targets.includes(targetMatch[1])) {
        targets.push(targetMatch[1]);
      }
    }

    if (/^\s*],?$/.test(line)) {
      currentSource = null;
    }
  }

  return childrenBySource;
}

function buildParentMap(childrenBySource) {
  const parents = new Map();

  for (const [source, targets] of childrenBySource.entries()) {
    for (const target of targets) {
      if (!parents.has(target)) {
        parents.set(target, source);
      }
    }
  }

  return parents;
}

function getFamilyRootEnum(enumKey, parentsByChild) {
  let current = enumKey;
  while (parentsByChild.has(current)) {
    current = parentsByChild.get(current);
  }
  return current;
}

function getFamilyDepth(enumKey, parentsByChild) {
  let depth = 0;
  let current = enumKey;
  while (parentsByChild.has(current)) {
    current = parentsByChild.get(current);
    depth += 1;
  }
  return depth;
}

function hasBranchAncestor(enumKey, parentsByChild, childrenBySource) {
  let current = enumKey;
  while (parentsByChild.has(current)) {
    const parent = parentsByChild.get(current);
    if ((childrenBySource.get(parent) ?? []).length > 1) {
      return true;
    }
    current = parent;
  }
  return false;
}

function buildFamilyRootInfo(rootLocaleKey, metadata, atomPools) {
  const override = FAMILY_ROOT_OVERRIDES[rootLocaleKey];
  if (override) {
    return override;
  }

  const used = [];
  const categoryAtom = pickCategoryAtom(metadata.category, atomPools, `${rootLocaleKey}:root:category`, used);
  if (categoryAtom) {
    used.push(categoryAtom);
  }

  const primaryAtom = pickTypeAtom(metadata.primaryType, atomPools, `${rootLocaleKey}:root:primary`, used);
  if (primaryAtom) {
    used.push(primaryAtom);
  }

  const secondaryAtom = metadata.secondaryType
    ? pickTypeAtom(metadata.secondaryType, atomPools, `${rootLocaleKey}:root:secondary`, used)
    : null;

  const words = unique([categoryAtom, primaryAtom, secondaryAtom].filter(Boolean)).slice(0, 2);

  if (words.length === 0) {
    words.push(pickTraitAtom(atomPools, ["wild"], `${rootLocaleKey}:root:fallback`) ?? "tralala");
  }

  if (words.length === 1) {
    const extra = pickTraitAtom(
      atomPools,
      TYPE_TRAITS[metadata.primaryType] ?? ["wild"],
      `${rootLocaleKey}:root:extra`,
      words,
    );
    if (extra) {
      words.push(extra);
    }
  }

  return {
    rootString: words.join(" "),
    baseWords: words,
  };
}

function getStageToken(rootLocaleKey, depth) {
  if (depth <= 0) {
    return null;
  }

  const override = FAMILY_ROOT_OVERRIDES[rootLocaleKey];
  if (override?.stageTokens?.[depth]) {
    return override.stageTokens[depth];
  }

  return pick(STAGE_TOKENS[Math.min(depth, STAGE_TOKENS.length - 1)], `${rootLocaleKey}:stage:${depth}`);
}

function getBranchToken(localeKey, metadata, atomPools, used = []) {
  const regionPrefix = getRegionPrefix(localeKey);
  if (regionPrefix) {
    return pick(REGION_TOKENS[regionPrefix] ?? COLLISION_TOKENS, `${localeKey}:region`);
  }

  const branchAtom = pickTypeAtom(
    metadata.secondaryType ?? metadata.primaryType,
    atomPools,
    `${localeKey}:branch`,
    used,
  );
  if (branchAtom) {
    return branchAtom;
  }

  return pick(
    COLLISION_TOKENS.filter(token => !used.includes(token)),
    `${localeKey}:branch:fallback`,
  );
}

function buildNameWords(rootInfo, rootLocaleKey, localeKey, metadata, depth, branched, atomPools) {
  if (depth === 0) {
    return rootInfo.rootString.split(/\s+/).filter(Boolean);
  }

  const words = [...rootInfo.baseWords];

  if (branched) {
    const branchToken = getBranchToken(localeKey, metadata, atomPools, words);
    if (branchToken && !words.includes(branchToken)) {
      words.push(branchToken);
    }
  } else {
    const stageToken = getStageToken(rootLocaleKey, depth);
    if (stageToken && !words.includes(stageToken)) {
      words.push(stageToken);
    }
  }

  return words.slice(0, 3);
}

function ensureUniqueName(words, localeKey, usedNames) {
  let candidateWords = words.slice(0, 3);
  let candidate = candidateWords.join(" ");

  for (
    let attempt = 0;
    attempt < 24 && usedNames.has(candidate) && usedNames.get(candidate) !== localeKey;
    attempt += 1
  ) {
    const extra = pick(COLLISION_TOKENS, `${localeKey}:collision:${attempt}`);
    candidateWords = candidateWords.filter(word => word !== extra);
    if (candidateWords.length >= 3) {
      candidateWords[candidateWords.length - 1] = extra;
    } else {
      candidateWords.push(extra);
    }
    candidate = candidateWords.slice(0, 3).join(" ");
  }

  if (usedNames.has(candidate) && usedNames.get(candidate) !== localeKey) {
    const prefix = candidateWords.slice(0, 2);
    for (let attempt = 0; attempt < FALLBACK_COLLISION_TOKENS.length; attempt += 1) {
      const extra = pick(FALLBACK_COLLISION_TOKENS, `${localeKey}:fallback:${attempt}`);
      candidate = [...prefix, extra].slice(0, 3).join(" ");
      if (!usedNames.has(candidate) || usedNames.get(candidate) === localeKey) {
        return candidate;
      }
    }
  }

  return candidate;
}

async function loadJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, "utf8"));
}

async function writeJson(filePath, value) {
  await fs.writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`);
}

async function main() {
  const englishPokemon = await loadJson(ENGLISH_POKEMON_FILE);
  const speciesSource = await fs.readFile(SPECIES_SOURCE_FILE, "utf8");
  const evolutionsSource = await fs.readFile(EVOLUTIONS_SOURCE_FILE, "utf8");
  const megalist = await loadJson(MEGALIST_FILE);
  const atomPools = buildAtomPools(megalist);
  const metadataByEnumKey = parseSpeciesMetadata(speciesSource);
  const childrenBySource = parseEvolutionGraph(evolutionsSource);
  const parentsByChild = buildParentMap(childrenBySource);
  const localeEntries = await fs.readdir(LOCALES_DIR, { withFileTypes: true });
  const generatedNames = new Map();
  const usedNames = new Map();
  const enumToLocaleKey = new Map(
    Object.keys(englishPokemon).map(localeKey => [localeKeyToEnumKey(localeKey), localeKey]),
  );
  const familyRootInfos = new Map();

  for (const localeKey of Object.keys(englishPokemon)) {
    const enumKey = localeKeyToEnumKey(localeKey);
    const metadata = metadataByEnumKey.get(enumKey);

    if (!metadata) {
      throw new Error(`Missing species metadata for ${localeKey} (${enumKey})`);
    }

    const familyRootEnum = getFamilyRootEnum(enumKey, parentsByChild);
    const familyRootLocaleKey = enumToLocaleKey.get(familyRootEnum);
    const familyRootMetadata = metadataByEnumKey.get(familyRootEnum);

    if (!familyRootLocaleKey || !familyRootMetadata) {
      throw new Error(`Missing family root metadata for ${localeKey} (${familyRootEnum})`);
    }

    if (!familyRootInfos.has(familyRootEnum)) {
      familyRootInfos.set(familyRootEnum, buildFamilyRootInfo(familyRootLocaleKey, familyRootMetadata, atomPools));
    }

    const rootInfo = familyRootInfos.get(familyRootEnum);
    const depth = getFamilyDepth(enumKey, parentsByChild);
    const branched = hasBranchAncestor(enumKey, parentsByChild, childrenBySource);
    const nameWords = buildNameWords(rootInfo, familyRootLocaleKey, localeKey, metadata, depth, branched, atomPools);
    const candidate = ensureUniqueName(nameWords, localeKey, usedNames);

    generatedNames.set(localeKey, candidate);
    usedNames.set(candidate, localeKey);
  }

  let updatedLocaleFiles = 0;

  for (const localeEntry of localeEntries) {
    if (!localeEntry.isDirectory()) {
      continue;
    }

    const localePokemonFile = path.join(LOCALES_DIR, localeEntry.name, "pokemon.json");

    try {
      await fs.access(localePokemonFile);
      const localePokemon = await loadJson(localePokemonFile);
      const rewrittenPokemon = {};

      for (const localeKey of Object.keys(englishPokemon)) {
        rewrittenPokemon[localeKey] = generatedNames.get(localeKey);
      }

      for (const extraKey of Object.keys(localePokemon)) {
        if (!(extraKey in rewrittenPokemon)) {
          rewrittenPokemon[extraKey] = localePokemon[extraKey];
        }
      }

      await writeJson(localePokemonFile, rewrittenPokemon);
      updatedLocaleFiles += 1;
    } catch {}
  }

  console.log(`Updated wiki-driven brainrot species names in ${updatedLocaleFiles} locale files.`);
  for (const localeKey of SAMPLE_KEYS) {
    console.log(`${localeKey}: ${generatedNames.get(localeKey)}`);
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});

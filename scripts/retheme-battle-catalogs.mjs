import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const LOCALES_DIR = path.join(ROOT, "locales");

const FILES = {
  ability: "ability.json",
  abilityTrigger: "ability-trigger.json",
  modifierType: "modifier-type.json",
  berry: "berry.json",
  moveTrigger: "move-trigger.json",
  battle: "battle.json",
  modifierSelect: "modifier-select-ui-handler.json",
  tutorial: "tutorial.json",
};

const PLACEHOLDER_PATTERN = /{{[^}]+}}/g;
const FALLBACK_ABILITY_PREFIXES = ["Wild", "Prime", "Null", "Arc", "Rush", "Ghost"];

const ABILITY_EXACT_OVERRIDES = {
  stench: "Reek Cloud",
  drizzle: "Raincall",
  speedBoost: "Quickclock",
  battleArmor: "Warhide",
  sturdy: "Last Stand",
  damp: "Blast Brake",
  limber: "Elastic Frame",
  sandVeil: "Dust Veil",
  static: "Sparkfield",
  voltAbsorb: "Volt Drink",
  waterAbsorb: "Tide Drink",
  oblivious: "Head Empty",
  cloudNine: "Weather Null",
  compoundEyes: "Keen Array",
  insomnia: "Wake Lock",
  flashFire: "Heat Feed",
  shieldDust: "Dust Ward",
  ownTempo: "Self Sync",
  intimidate: "Mean Mug",
  shadowTag: "Shade Snare",
  roughSkin: "Barbed Hide",
  wonderGuard: "Odd Guard",
  levitate: "Hover Drift",
  effectSpore: "Sporeburst",
  synchronize: "Mirror Pulse",
  immunity: "Clean Blood",
  naturalCure: "Cleanse",
  lightningRod: "Volt Beacon",
  sereneGrace: "Calm Grace",
  swiftSwim: "Rain Rush",
  chlorophyll: "Sunleaf",
  trace: "Copyprint",
  hugePower: "Big Hands",
  soundproof: "Soundseal",
  sandStream: "Duststream",
  pressure: "Crush Aura",
  flameBody: "Ember Hide",
  keenEye: "Needle Eye",
  pickup: "Scavenge",
  truant: "Slack Loop",
  hustle: "Overdrive",
  cuteCharm: "Charm Pulse",
  plus: "Plus Drive",
  minus: "Minus Drive",
  stickyHold: "Stickfast",
  guts: "Grit",
  overgrow: "Overbloom",
  blaze: "Heat Surge",
  torrent: "Undertow",
  swarm: "Mob Rush",
  drought: "Suncall",
  arenaTrap: "Ground Snare",
  vitalSpirit: "Livewire",
  whiteSmoke: "White Haze",
  purePower: "Pure Force",
  airLock: "Sky Lock",
  motorDrive: "Motor Feed",
  rivalry: "Clash Instinct",
  steadfast: "Firm Step",
  snowCloak: "Frost Veil",
  gluttony: "Greed Drive",
  angerPoint: "Fury Point",
  unburden: "Dropstep",
  heatproof: "Heatshield",
  download: "Load In",
  ironFist: "Steel Fist",
  poisonHeal: "Venom Mend",
  adaptability: "Flex Sync",
  skillLink: "Chain Link",
  hydration: "Hydro Sync",
  solarPower: "Sun Charge",
  quickFeet: "Quickstep",
  sniper: "Deadeye",
  magicGuard: "Hex Guard",
  noGuard: "All In",
  technician: "Microcraft",
  moldBreaker: "Pattern Break",
  superLuck: "Lucky Break",
  aftermath: "Backblast",
  anticipation: "Premonition",
  forewarn: "Omen Sense",
  unaware: "Blank Mind",
  tintedLens: "Tint Lens",
  slowStart: "Cold Start",
  scrappy: "Street Brawl",
  stormDrain: "Storm Siphon",
  snowWarning: "Frost Warning",
  honeyGather: "Nectar Gather",
  frisk: "Patdown",
  reckless: "Wild Swing",
};

const ABILITY_WORD_OVERRIDES = new Map([
  ["boost", "surge"],
  ["armor", "hide"],
  ["absorb", "drink"],
  ["color", "hue"],
  ["change", "shift"],
  ["shadow", "shade"],
  ["tag", "snare"],
  ["rough", "barbed"],
  ["skin", "hide"],
  ["guard", "ward"],
  ["lightning", "volt"],
  ["rod", "beacon"],
  ["swift", "rain"],
  ["swim", "rush"],
  ["huge", "big"],
  ["power", "force"],
  ["flame", "ember"],
  ["pickup", "scavenge"],
  ["hustle", "drive"],
  ["drought", "suncall"],
  ["arena", "ground"],
  ["trap", "snare"],
  ["motor", "volt"],
  ["gluttony", "greed"],
  ["adaptability", "flex"],
  ["technician", "craft"],
  ["pressure", "crush"],
  ["frisk", "patdown"],
]);

const ITEM_NAME_OVERRIDES = {
  PokemonNatureChangeModifierType: "{{natureName}} Tonic",
  PokemonBaseStatFlatModifierType: "Dream Cake",
  TmModifierType: "BrainDance {{moveId}} - {{moveName}}",
  TmModifierTypeWithInfo: "BrainDance {{moveId}} - {{moveName}}",
  TerastallizeModifierType: "{{teraType}} Prism Shard",
  MEGA_BRACELET: "Overdrive Rig",
  DYNAMAX_BAND: "Titan Strap",
  TERA_ORB: "Prism Core",
  MAP: "Route Map",
  REVIVER_SEED: "Second Wind Seed",
  WHITE_HERB: "Blank Herb",
  OVAL_CHARM: "Nest Charm",
  EXP_CHARM: "Growth Charm",
  SUPER_EXP_CHARM: "Growth Charm+",
  GOLDEN_EXP_CHARM: "Golden Growth Charm",
  SOOTHE_BELL: "Calm Bell",
  SCOPE_LENS: "Weakpoint Lens",
  LEEK: "Long Stalk",
  EVIOLITE: "Mutastone",
  SOUL_DEW: "Soul Mist",
  NUGGET: "Gold Chunk",
  BIG_NUGGET: "Big Gold Chunk",
  AMULET_COIN: "Lucky Coin",
  COIN_CASE: "Cash Case",
  LOCK_CAPSULE: "Lock Case",
  GRIP_CLAW: "Snare Claw",
  WIDE_LENS: "Broad Lens",
  MULTI_LENS: "Split Lens",
  BERRY_POUCH: "Zaza Stash",
  FOCUS_BAND: "Resolve Band",
  QUICK_CLAW: "Snap Claw",
  KINGS_ROCK: "Monarch Rock",
  LEFTOVERS: "Scraps",
  SHELL_BELL: "Echo Shell",
  TOXIC_ORB: "Venom Core",
  FLAME_ORB: "Ember Core",
  MYSTICAL_ROCK: "Mythic Rock",
  BATON: "Relay Baton",
  DNA_SPLICERS: "Gene Splicers",
  MINI_BLACK_HOLE: "Gravity Knot",
  MYSTERY_ENCOUNTER_BLACK_SLUDGE: "Tar Sludge",
  MYSTERY_ENCOUNTER_MACHO_BRACE: "Power Strap",
  MYSTERY_ENCOUNTER_OLD_GATEAU: "Dream Cake",
};

const ITEM_DESCRIPTION_OVERRIDES = {
  PokemonNatureChangeModifierType:
    "Changes a Mogger Mon’s nature to {{natureName}} and permanently unlocks the nature for the recruit.",
  TmModifierType: "Load {{moveName}} onto a Mogger Mon with a BrainDance disc.",
  TmModifierTypeWithInfo:
    "Load {{moveName}} onto a Mogger Mon with a BrainDance disc.\n(Hold C or Shift for more info).",
  TerastallizeModifierType: "Changes the Mogger Mon’s Prism type to {{teraType}}.",
  MEGA_BRACELET: "Overdrive Stones become available.",
  DYNAMAX_BAND: "Titan Caps become available.",
  TERA_ORB: "Allows your Mogger Mon to Prism Shift. Recharges slowly. Prism Shards also become available.",
};

const BERRY_NAME_OVERRIDES = {
  sitrus: "Pulse Zaza",
  lum: "Clear Zaza",
  enigma: "Glitch Zaza",
  liechi: "Rage Zaza",
  ganlon: "Guard Zaza",
  petaya: "Amp Zaza",
  apicot: "Shell Zaza",
  salac: "Rush Zaza",
  lansat: "Scope Zaza",
  starf: "Chaos Zaza",
  leppa: "Charge Zaza",
};

const CATALOG_TERM_REPLACEMENTS = [
  [/\bmove sets\b/gi, "technique sets"],
  [/\bmovesets\b/gi, "technique sets"],
  [/\bmove set\b/gi, "technique set"],
  [/\bmoveset\b/gi, "technique set"],
  [/\bAbilities\b/g, "Traits"],
  [/\babilities\b/g, "traits"],
  [/\bAbility\b/g, "Trait"],
  [/\bability\b/g, "trait"],
  [/\bItems\b/g, "Relics"],
  [/\bitems\b/g, "relics"],
  [/\bItem\b/g, "Relic"],
  [/\bitem\b/g, "relic"],
  [/\bMoves\b/g, "Techniques"],
  [/\bmoves\b/g, "techniques"],
  [/\bMove\b/g, "Technique"],
  [/\bmove\b/g, "technique"],
  [/\bBerries\b/g, "Zaza"],
  [/\bberries\b/g, "zaza"],
  [/\bBerry\b/g, "Zaza"],
  [/\bberry\b/g, "zaza"],
  [/\bPok[eé]balls\b/g, "Cryotanks"],
  [/\bPok[eé]ball\b/g, "Cryotank"],
  [/\bTM Moves\b/g, "BrainDances"],
  [/\bTM Move\b/g, "BrainDance"],
  [/\bTMs\b/g, "BrainDances"],
  [/\bTM\b/g, "BrainDance"],
  [/\bModules\b/g, "BrainDances"],
  [/\bModule\b/g, "BrainDance"],
  [/\bBrainces\b/g, "BrainDances"],
  [/\bBraince\b/g, "BrainDance"],
  [/\bbrainces\b/g, "braindances"],
  [/\bbraince\b/g, "braindance"],
  [/\bCryptanks\b/g, "Cryotanks"],
  [/\bCryptank\b/g, "Cryotank"],
  [/\bcryptanks\b/g, "cryotanks"],
  [/\bcryptank\b/g, "cryotank"],
  [/\bAn relic\b/g, "A relic"],
  [/\ban relic\b/g, "a relic"],
  [/\bTera type\b/g, "Prism type"],
  [/\bTerastallize\b/g, "Prism Shift"],
  [/\bTerastallization\b/g, "Prism Shift"],
  [/\bstarter\b/gi, match => (match[0] === match[0].toUpperCase() ? "Recruit" : "recruit")],
  [/\bSnack Pouch\b/g, "Zaza Stash"],
  [/\bsnack pouch\b/g, "zaza stash"],
  [/\bSnacks\b/g, "Zaza"],
  [/\bsnacks\b/g, "zaza"],
  [/\bSnack\b/g, "Zaza"],
  [/\bsnack\b/g, "zaza"],
];

function toTitleCase(value) {
  return value
    .split(/\s+/)
    .filter(Boolean)
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

function hashString(value) {
  let hash = 0;
  for (const char of value) {
    hash = (hash * 31 + char.charCodeAt(0)) | 0;
  }
  return Math.abs(hash);
}

function normalizeWords(value) {
  return value
    .replace(/['’.:,!?()]/g, " ")
    .replace(/&/g, " and ")
    .replace(/\//g, " ")
    .split(/[\s-]+/)
    .map(word => word.trim())
    .filter(Boolean);
}

function keyToWords(key) {
  return key
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .split(/\s+/)
    .filter(Boolean);
}

function maskPlaceholders(value) {
  const placeholders = [];
  const masked = value.replace(PLACEHOLDER_PATTERN, placeholder => {
    const index = placeholders.push(placeholder) - 1;
    return `__ROT_PLACEHOLDER_${index}__`;
  });
  return { masked, placeholders };
}

function restorePlaceholders(value, placeholders) {
  return value.replace(/__ROT_PLACEHOLDER_(\d+)__/g, (_match, index) => placeholders[Number(index)] ?? "");
}

function replaceCatalogTerms(value) {
  if (typeof value !== "string") {
    return value;
  }

  const { masked, placeholders } = maskPlaceholders(value);
  let output = masked;
  for (const [pattern, replacement] of CATALOG_TERM_REPLACEMENTS) {
    output = output.replace(pattern, replacement);
  }
  return restorePlaceholders(output, placeholders);
}

function transformStrings(value) {
  if (typeof value === "string") {
    return replaceCatalogTerms(value);
  }
  if (Array.isArray(value)) {
    return value.map(transformStrings);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, transformStrings(child)]));
  }
  return value;
}

function transformAbilityName(key, originalName) {
  if (ABILITY_EXACT_OVERRIDES[key]) {
    return ABILITY_EXACT_OVERRIDES[key];
  }

  const sourceWords = normalizeWords(originalName || keyToWords(key).join(" "));
  const replacedWords = sourceWords.flatMap(word => {
    const replacement = ABILITY_WORD_OVERRIDES.get(word.toLowerCase());
    return replacement ? replacement.split(/\s+/) : [word];
  });
  let result = toTitleCase(replacedWords.join(" "));
  const normalizedOriginal = toTitleCase(sourceWords.join(" "));

  if (!result || result.toLowerCase() === normalizedOriginal.toLowerCase()) {
    const prefix = FALLBACK_ABILITY_PREFIXES[hashString(key) % FALLBACK_ABILITY_PREFIXES.length];
    result = `${prefix} ${normalizedOriginal}`;
  }

  return result;
}

async function loadJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, "utf8"));
}

async function writeJson(filePath, value) {
  await fs.writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`);
}

async function updateAbilityFiles(localeDir, englishAbilityData, englishAbilityTriggerData) {
  const abilityFile = path.join(localeDir, FILES.ability);
  const abilityTriggerFile = path.join(localeDir, FILES.abilityTrigger);

  try {
    await fs.access(abilityFile);
    const rewritten = {};
    for (const [abilityKey, englishEntry] of Object.entries(englishAbilityData)) {
      rewritten[abilityKey] = {
        name: transformAbilityName(abilityKey, englishEntry.name ?? keyToWords(abilityKey).join(" ")),
        description: replaceCatalogTerms(englishEntry.description ?? ""),
      };
    }
    await writeJson(abilityFile, rewritten);
  } catch {
    // Ignore locales without ability.json.
  }

  try {
    await fs.access(abilityTriggerFile);
    await writeJson(abilityTriggerFile, transformStrings(englishAbilityTriggerData));
  } catch {
    // Ignore locales without ability-trigger.json.
  }
}

async function updateModifierTypeFile(localeDir, englishModifierTypeData) {
  const modifierTypeFile = path.join(localeDir, FILES.modifierType);
  try {
    await fs.access(modifierTypeFile);
    const rewrittenModifierTypes = {};
    for (const [modifierKey, englishEntry] of Object.entries(englishModifierTypeData.ModifierType)) {
      const entry = transformStrings(englishEntry);
      if (entry.name) {
        entry.name = ITEM_NAME_OVERRIDES[modifierKey] ?? replaceCatalogTerms(entry.name);
      }
      if (entry.description) {
        entry.description = ITEM_DESCRIPTION_OVERRIDES[modifierKey] ?? replaceCatalogTerms(entry.description);
      }
      if (entry.extra) {
        entry.extra = transformStrings(entry.extra);
      }
      rewrittenModifierTypes[modifierKey] = entry;
    }
    await writeJson(modifierTypeFile, { ModifierType: rewrittenModifierTypes });
  } catch {
    // Ignore locales without modifier-type.json.
  }
}

async function updateBerryFile(localeDir, englishBerryData) {
  const berryFile = path.join(localeDir, FILES.berry);
  try {
    await fs.access(berryFile);
    const rewritten = {};
    for (const [berryKey, englishEntry] of Object.entries(englishBerryData)) {
      rewritten[berryKey] = {
        name:
          BERRY_NAME_OVERRIDES[berryKey] ?? replaceCatalogTerms(englishEntry.name ?? keyToWords(berryKey).join(" ")),
        effect: replaceCatalogTerms(englishEntry.effect ?? ""),
      };
    }
    await writeJson(berryFile, rewritten);
  } catch {
    // Ignore locales without berry.json.
  }
}

async function updateGenericCatalogFiles(localeDir, englishFiles) {
  for (const [fileName, englishData] of Object.entries(englishFiles)) {
    const localeFile = path.join(localeDir, fileName);
    try {
      await fs.access(localeFile);
      await writeJson(localeFile, transformStrings(englishData));
    } catch {
      // Ignore missing locale files.
    }
  }
}

async function main() {
  const englishDir = path.join(LOCALES_DIR, "en");
  const englishAbilityData = await loadJson(path.join(englishDir, FILES.ability));
  const englishAbilityTriggerData = await loadJson(path.join(englishDir, FILES.abilityTrigger));
  const englishModifierTypeData = await loadJson(path.join(englishDir, FILES.modifierType));
  const englishBerryData = await loadJson(path.join(englishDir, FILES.berry));
  const englishGenericFiles = Object.fromEntries(
    await Promise.all(
      [FILES.moveTrigger, FILES.battle, FILES.modifierSelect, FILES.tutorial].map(async fileName => [
        fileName,
        await loadJson(path.join(englishDir, fileName)),
      ]),
    ),
  );

  const localeEntries = await fs.readdir(LOCALES_DIR, { withFileTypes: true });
  let updatedLocales = 0;

  for (const localeEntry of localeEntries) {
    if (!localeEntry.isDirectory()) {
      continue;
    }

    const localeDir = path.join(LOCALES_DIR, localeEntry.name);
    await updateAbilityFiles(localeDir, englishAbilityData, englishAbilityTriggerData);
    await updateModifierTypeFile(localeDir, englishModifierTypeData);
    await updateBerryFile(localeDir, englishBerryData);
    await updateGenericCatalogFiles(localeDir, englishGenericFiles);
    updatedLocales += 1;
  }

  console.log(`Rethemed battle catalogs in ${updatedLocales} locale directories.`);
  console.log(
    `Sample ability names: drizzle -> ${transformAbilityName("drizzle", englishAbilityData.drizzle.name)}, `
      + `intimidate -> ${transformAbilityName("intimidate", englishAbilityData.intimidate.name)}, `
      + `pickup -> ${transformAbilityName("pickup", englishAbilityData.pickup.name)}`,
  );
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});

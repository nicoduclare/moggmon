import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const LOCALES_EN_DIR = path.join(ROOT, "locales", "en");
const MYSTERY_ENCOUNTERS_DIR = path.join(LOCALES_EN_DIR, "mystery-encounters");

const PLACEHOLDER_PATTERN = /{{[^}]+}}/g;

const FILES = [
  path.join(LOCALES_EN_DIR, "move.json"),
  path.join(LOCALES_EN_DIR, "bgm-name.json"),
  path.join(LOCALES_EN_DIR, "splash-texts.json"),
];

const BASE_REPLACEMENTS = [
  [/\bPok[eé]mon\b/g, "Mogger Mon"],
  [/\bpok[eé]mon\b/g, "Mogger Mon"],
  [/\bAbilities\b/g, "Traits"],
  [/\babilities\b/g, "traits"],
  [/\bAbility\b/g, "Trait"],
  [/\bability\b/g, "trait"],
  [/\bSnacks\b/g, "Zaza"],
  [/\bsnacks\b/g, "zaza"],
  [/\bSnack\b/g, "Zaza"],
  [/\bsnack\b/g, "zaza"],
  [/\bBerries\b/g, "Zaza"],
  [/\bberries\b/g, "zaza"],
  [/\bBerry\b/g, "Zaza"],
  [/\bberry\b/g, "zaza"],
  [/\bPok[eé]balls\b/g, "Cryotanks"],
  [/\bPok[eé]ball\b/g, "Cryotank"],
  [/\bTMs\b/g, "BrainDances"],
  [/\bTM\b/g, "BrainDance"],
  [/\bModules\b/g, "BrainDances"],
  [/\bModule\b/g, "BrainDance"],
  [/\bmodules\b/g, "braindances"],
  [/\bmodule\b/g, "braindance"],
  [/\bBrainces\b/g, "BrainDances"],
  [/\bBraince\b/g, "BrainDance"],
  [/\bbrainces\b/g, "braindances"],
  [/\bbraince\b/g, "braindance"],
  [/\bCryptanks\b/g, "Cryotanks"],
  [/\bCryptank\b/g, "Cryotank"],
  [/\bcryptanks\b/g, "cryotanks"],
  [/\bcryptank\b/g, "cryotank"],
  [/\bEvolution\b/g, "Maxx"],
  [/\bevolution\b/g, "maxx"],
  [
    /\bmutat(?:e|ion|ing)\b/gi,
    match => {
      if (match[0] === "M") {
        if (match === "Mutation") {
          return "Maxx";
        }
        if (match === "Mutate") {
          return "Maxx";
        }
        if (match === "Mutating") {
          return "Maxxing";
        }
      }
      if (match === "mutation") {
        return "maxx";
      }
      if (match === "mutate") {
        return "maxx";
      }
      if (match === "mutating") {
        return "maxxing";
      }
      return match;
    },
  ],
];

const MOVE_REPLACEMENTS = [
  [/\bAfter obtaining Z-Power\b/g, "After hitting full Maxx charge"],
  [/\busing its Z-Power\b/g, "using full Maxx charge"],
  [/\busing their Z-Power\b/g, "using full Maxx charge"],
  [/\bwith the full force of its Z-Power\b/g, "with full Maxx force"],
  [
    /\bwith full force with threads of silk that the user spits using its Z-Power\b/g,
    "with silk threads spun at full Maxx charge",
  ],
  [
    /\bZ-Power brings out the true capabilities of the user\b/g,
    "Full Maxx charge brings out the user’s full potential",
  ],
  [/\bZ-Power\b/g, "Maxx charge"],
  [/\bThe user, [^,]+, /g, "The user "],
  [/\bthe user, [^,]+, /g, "the user "],
  [/\bwearing a cap\b/g, "in full stunt gear"],
  [/\bPikachu loves its Trainer\b/g, "the user syncs with its trainer"],
  [/\bEevee loves its Trainer\b/g, "the user syncs with its trainer"],
  [/\bobtains Alola’s energy\b/g, "channels old-world energy"],
  [/\bAlola’s energy\b/g, "old-world energy"],
  [/\bthe Land Spirit Mogger Mon\b/g, "the land-guardian Mogger Mon"],
  [/\bGigantamax [^.]+ use\b/g, "a full-Maxx titan can unleash"],
  [/\bGigantamax\b/g, "full-Maxx"],
  [/\b(?:Ultra|Turbo|Giga|Big|Hyper|Mega)\s+G Max\s+/g, "Titan "],
  [/\bG Max\s+/g, "Titan "],
  [/\bMax Guard\b/g, "Null Guard"],
  [/\bCatastropika\b/g, "Catastrozap"],
  [/\bPika Papow\b/g, "Volt Papow"],
  [/\bVeevee Volley\b/g, "Buddy Volley"],
  [/\bGuardian Of Alola\b/g, "Guardian Break"],
  [/\bSinister Arrow Raid\b/g, "Phantom Arrow Raid"],
  [/\bExtreme Evoboost\b/g, "Extreme Boostdrive"],
  [/\bPhoton Geyser\b/g, "Prism Geyser"],
  [/\bLight That Burns The Sky\b/g, "Skyburn Prism"],
  [/\bSearing Sunraze Smash\b/g, "Searing Sunsmash"],
  [/\bMenacing Moonraze Maelstrom\b/g, "Menacing Moonstorm"],
  [/\bLets Snuggle Forever\b/g, "Snuggle Crash"],
  [/\bTen Million Volt Thunderbolt\b/g, "Ten Million Volt Burst"],
  [/\bNecrozma\b/g, "the user"],
  [/\bSolgaleo\b/g, "the user"],
  [/\bLunala\b/g, "the user"],
  [/\bPikachu\b/g, "the user"],
  [/\bDecidueye\b/g, "the user"],
  [/\bIncineroar\b/g, "the user"],
  [/\bPrimarina\b/g, "the user"],
  [/\bMarshadow\b/g, "the user"],
  [/\bAlolan Raichu\b/g, "the user"],
  [/\bSnorlax\b/g, "the user"],
  [/\bEevee\b/g, "the user"],
  [/\bMew\b/g, "the user"],
  [/\bMimikyu\b/g, "the user"],
  [/\bLycanroc\b/g, "the user"],
  [/\bKommo-o\b/g, "the user"],
];

const BGM_REPLACEMENTS = [
  [/\bEmerald Mew Battle\b/g, "Mythic Signal Battle"],
  [/\bSM Solgaleo & Lunala Battle\b/g, "Sun and Moon Titan Battle"],
  [/\bUSUM Dusk Mane & Dawn Wings Necrozma Battle\b/g, "Twin Prism Battle"],
  [/\bUSUM Ultra Necrozma Battle\b/g, "Prism Tyrant Battle"],
  [/\bZA Rogue Mega Battle\b/g, "Rogue Titan Battle"],
  [/\bBW Pokémon Heal\b/g, "Heal Jingle"],
  [/Welcome to the World of Pokémon!/g, "Welcome to Mogger Mon!"],
];

const SPLASH_REPLACEMENTS = [
  [/Also Try Pokéngine!/g, "Build Your Own Weird Team!"],
  [/Also Try Emerald Rogue!/g, "Touch Grass Between Runs!"],
  [/Also Try Radical Red!/g, "Try a Meaner Seed!"],
  [/Eevee Expo!/g, "Signal Expo!"],
  [/Also Try Mogger Mon! Wait\.\.\./g, "You’re Already Here!"],
  [/Basic Reading Trait Recommended!/g, "Basic Reading Skills Recommended!"],
  [/Holiday Style Pikachu Not Included!/g, "Holiday Mascot Not Included!"],
  [/Yache/g, "Crunch"],
  [/TM Shop/g, "BrainDance Booth"],
];

const POST_RESTORE_REPLACEMENTS = {
  "splash-texts.json": [
    [/Don't Talk About the {{pokemonName}} Outage!/g, "Don't Talk About the {{pokemonName}} Incident!"],
  ],
};

const MYSTERY_REPAIRS = [
  [/Time to technique on\./g, "Time to move on."],
  [/techniques across/g, "moves across"],
  [/techniques to defend itself/g, "moves to defend itself"],
  [/get it to technique/g, "get it to move"],
];

const MOVE_REPAIRS = [
  [/can’t technique on the next turn/g, "can’t act on the next turn"],
  [
    /If used by Ash Greninja, This technique gains more power and the target is always hit three times in a row\./g,
    "In its sharpened form, this technique gains more power and always hits three times in a row.",
  ],
  [
    /The user attacks twice using Dreepy\. If there are two targets, This technique hits each target once\./g,
    "The user attacks twice with guided projectiles. If there are two targets, this technique hits each target once.",
  ],
  [
    /If used by Morpeko, This technique’s type changes depending on the user’s form\./g,
    "In certain forms, this technique’s type changes with the user.",
  ],
  [
    /This is Eternatus’s most powerful attack in its original form\./g,
    "This is the user’s most powerful attack in its base form.",
  ],
  [
    /If the user has Terastallized, it unleashes energy of its Tera Type\./g,
    "If the user is prism-shifted, it unleashes energy of its prism type.",
  ],
  [
    /If the user has a Tatsugiri in its mouth, This technique boosts one of the user’s stats based on the Tatsugiri’s form\./g,
    "If the user has a partner loaded up, this technique boosts one of its stats based on that partner’s form.",
  ],
  [
    /When used by Terapagos in its Stellar Form, This technique damages all the other side\./g,
    "In its stellar form, this technique damages the entire opposing side.",
  ],
];

function protectPlaceholders(value) {
  const placeholders = [];
  const protectedValue = value.replace(PLACEHOLDER_PATTERN, match => {
    const token = `__PLACEHOLDER_${placeholders.length}__`;
    placeholders.push(match);
    return token;
  });
  return { protectedValue, placeholders };
}

function restorePlaceholders(value, placeholders) {
  return placeholders.reduce(
    (output, placeholder, index) => output.replace(`__PLACEHOLDER_${index}__`, placeholder),
    value,
  );
}

function applyReplacements(value, replacements) {
  let next = value;
  for (const [pattern, replacement] of replacements) {
    next = next.replace(pattern, replacement);
  }
  return next;
}

function transformString(filePath, value) {
  const { protectedValue, placeholders } = protectPlaceholders(value);
  let next = applyReplacements(protectedValue, BASE_REPLACEMENTS);
  if (filePath.endsWith("move.json")) {
    next = applyReplacements(next, MOVE_REPLACEMENTS);
  }
  if (filePath.endsWith("bgm-name.json")) {
    next = applyReplacements(next, BGM_REPLACEMENTS);
  }
  if (filePath.endsWith("splash-texts.json")) {
    next = applyReplacements(next, SPLASH_REPLACEMENTS);
  }
  next = restorePlaceholders(next, placeholders);
  for (const [fileName, replacements] of Object.entries(POST_RESTORE_REPLACEMENTS)) {
    if (filePath.endsWith(fileName)) {
      next = applyReplacements(next, replacements);
    }
  }
  if (filePath.endsWith("move.json")) {
    next = applyReplacements(next, MOVE_REPAIRS);
  }
  if (filePath.includes(`${path.sep}mystery-encounters${path.sep}`)) {
    next = applyReplacements(next, MYSTERY_REPAIRS);
  }
  return next;
}

function transformNode(filePath, node) {
  if (typeof node === "string") {
    return transformString(filePath, node);
  }
  if (Array.isArray(node)) {
    return node.map(item => transformNode(filePath, item));
  }
  if (node && typeof node === "object") {
    return Object.fromEntries(Object.entries(node).map(([key, value]) => [key, transformNode(filePath, value)]));
  }
  return node;
}

async function* walkJsonFiles(rootDir) {
  const entries = await fs.readdir(rootDir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(rootDir, entry.name);
    if (entry.isDirectory()) {
      yield* walkJsonFiles(fullPath);
      continue;
    }
    if (entry.isFile() && entry.name.endsWith(".json")) {
      yield fullPath;
    }
  }
}

async function collectTargets() {
  const targets = [...FILES];
  for await (const filePath of walkJsonFiles(MYSTERY_ENCOUNTERS_DIR)) {
    targets.push(filePath);
  }
  return targets;
}

let changedFiles = 0;
for (const filePath of await collectTargets()) {
  const originalText = await fs.readFile(filePath, "utf8");
  const parsed = JSON.parse(originalText);
  const transformed = transformNode(filePath, parsed);
  const nextText = `${JSON.stringify(transformed, null, 2)}\n`;
  if (nextText !== originalText) {
    await fs.writeFile(filePath, nextText, "utf8");
    changedFiles += 1;
  }
}

console.log(`Finalized launch English copy in ${changedFiles} files.`);

import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const LOCALES_DIR = path.join(ROOT, "locales");
const ENGLISH_MOVE_FILE = path.join(LOCALES_DIR, "en", "move.json");
const ENGLISH_MOVE_TRIGGER_FILE = path.join(LOCALES_DIR, "en", "move-trigger.json");

const EXACT_OVERRIDES = {
  absorb: "Yoink",
  agility: "Zoomies",
  airSlash: "Sky Slice",
  amnesia: "Brain 404",
  aquaStep: "Wet Footwork",
  armorCannon: "Tank Blast",
  auraSphere: "Vibe Orb",
  bind: "Grabby Grab",
  bite: "Nom Nom",
  braveBird: "Bird Send",
  bugBuzz: "Bug Noise",
  bulletPunch: "Speed Bonk",
  calmMind: "Brain Spa",
  clamp: "Clamp Champ",
  closeCombat: "Throw Hands",
  collisionCourse: "Crash Out",
  confuseRay: "Confuse Beam",
  constrict: "Squeeze Mode",
  crunch: "Crunch Munch",
  darkPulse: "Edge Pulse",
  dig: "Dirt Hide",
  doubleEdge: "Double Ouch",
  doubleKick: "Kick Kick",
  doubleSlap: "Slap Slap",
  doubleTeam: "Clone Spam",
  drainPunch: "Yoink Bonk",
  dragonClaw: "Lizard Claw",
  dragonDarts: "Lizard Darts",
  dragonPulse: "Lizard Pulse",
  dreamEater: "Sleep Snack",
  earthQuake: "Ground Shake",
  earthquake: "Ground Shake",
  electroDrift: "Zap Slide",
  ember: "Lil Flame",
  extremeSpeed: "Max Zoom",
  fakeOut: "Cheap Shot",
  fellStinger: "Doom Poke",
  flamethrower: "Flame Yeet",
  flashCannon: "Laser Pot",
  fly: "Big Yeet",
  gigatonHammer: "Big Bonk",
  growl: "Grr Grr",
  headbutt: "Head Bonk",
  healingWish: "Heal Wish",
  hydroPump: "Mega Wet",
  hyperBeam: "Giga Laser",
  iceBeam: "Cold Laser",
  karateChop: "Dojo Chop",
  kinesis: "Spoon Trick",
  leechSeed: "Yoink Seed",
  luminaCrash: "Shine Crash",
  makeItRain: "Money Rain",
  matchaGotcha: "Tea Trap",
  moonblast: "Moon Boom",
  naturePower: "Nature Sauce",
  nuzzle: "Snuggle Zap",
  playRough: "Roughhouse",
  poisonGas: "Stinky Gas",
  poisonSting: "Stinky Poke",
  populationBomb: "Crowd Kaboom",
  pound: "Bonk Bonk",
  protect: "Nope Shield",
  psychic: "Brain Blast",
  psybeam: "Brain Laser",
  quickAttack: "Fast Bonk",
  rageFist: "Mad Mitt",
  razorLeaf: "Leaf Spam",
  razorWind: "Slicey Wind",
  recover: "Full Reset",
  rest: "Big Nap",
  roar: "Big Yell",
  saltCure: "Seasoning",
  safeguard: "Team Nope Field",
  scratch: "Scritch",
  shadowBall: "Spooky Orb",
  sing: "La La",
  sleepPowder: "Nap Dust",
  softBoiled: "Egg Heal",
  stealthRock: "Sneaky Rocks",
  stomp: "Stompy",
  supersonic: "Loud Loud",
  surf: "Wave Ride",
  swift: "Auto Zoom",
  tackle: "Bonk",
  tailWhip: "Tail Wiggle",
  takeDown: "Sit Down",
  teleport: "Blink",
  thunder: "Big Zap",
  thunderBolt: "Zap Zap",
  thunderPunch: "Zap Bonk",
  thunderShock: "Zap Buzz",
  thunderbolt: "Zap Zap",
  thundershock: "Zap Buzz",
  torchSong: "Fire Mixtape",
  toxic: "Stinky Max",
  vineWhip: "Plant Whap",
  waterGun: "Wet Wet",
  waterPulse: "Wet Pulse",
  whirlwind: "Spin Wind",
  willOWisp: "Ghost Lighter",
  xScissor: "X Snip",
};

const WORD_OVERRIDES = new Map([
  ["absorb", "yoink"],
  ["acid", "goop"],
  ["aero", "air"],
  ["aerial", "air"],
  ["air", "air"],
  ["alluring", "rizz"],
  ["aqua", "wet"],
  ["armor", "tank"],
  ["attack", "bonk"],
  ["barrage", "spam"],
  ["bash", "bonk"],
  ["beam", "laser"],
  ["beak", "beak"],
  ["bite", "nom"],
  ["blast", "boom"],
  ["blaze", "flame"],
  ["blizzard", "snow spam"],
  ["bolt", "zap"],
  ["bomb", "kaboom"],
  ["break", "break"],
  ["burning", "burnin"],
  ["burst", "boom"],
  ["buzz", "buzz"],
  ["cannon", "blast"],
  ["charge", "zoom"],
  ["chop", "chop"],
  ["claw", "claw"],
  ["clangorous", "loud"],
  ["close", "close"],
  ["combat", "hands"],
  ["comet", "space"],
  ["confusion", "brain lag"],
  ["crash", "crash"],
  ["crunch", "munch"],
  ["cut", "snip"],
  ["dance", "jig"],
  ["dark", "spooky"],
  ["desire", "want"],
  ["dig", "dirt hide"],
  ["doom", "doom"],
  ["double", "double"],
  ["drain", "yoink"],
  ["drill", "drill"],
  ["dynamax", "max"],
  ["earth", "ground"],
  ["edge", "edge"],
  ["electric", "zap"],
  ["electro", "zap"],
  ["ember", "lil flame"],
  ["eruption", "boom"],
  ["extreme", "max"],
  ["fake", "fake"],
  ["fang", "chomp"],
  ["feather", "bird"],
  ["fire", "hot"],
  ["fist", "mitt"],
  ["flame", "flame"],
  ["flare", "flame"],
  ["flash", "flash"],
  ["flight", "yeet"],
  ["flower", "petal"],
  ["focus", "lock in"],
  ["force", "force"],
  ["frost", "cold"],
  ["fury", "mad"],
  ["gear", "gear"],
  ["gigaton", "big"],
  ["glare", "stare"],
  ["gleam", "shine"],
  ["glow", "glow"],
  ["growl", "grr"],
  ["gun", "wet"],
  ["gust", "wind tap"],
  ["hammer", "bonk"],
  ["heat", "hot"],
  ["heart", "heart"],
  ["hex", "curse"],
  ["horn", "horn"],
  ["hurricane", "storm"],
  ["hydro", "wet"],
  ["hyper", "giga"],
  ["hypnosis", "sleep beam"],
  ["ice", "cold"],
  ["icy", "cold"],
  ["iron", "metal"],
  ["jab", "poke"],
  ["jet", "zoom"],
  ["jump", "hop"],
  ["kick", "kick"],
  ["laser", "laser"],
  ["leaf", "leaf"],
  ["leech", "yoink"],
  ["light", "shine"],
  ["lunar", "moon"],
  ["lumina", "shine"],
  ["mach", "zoom"],
  ["magical", "sparkle"],
  ["magnitude", "big shake"],
  ["mega", "mega"],
  ["metal", "metal"],
  ["mind", "brain"],
  ["moon", "moon"],
  ["mud", "mud"],
  ["mystical", "arcane"],
  ["night", "spooky"],
  ["noisy", "loud"],
  ["nova", "boom"],
  ["oze", "goop"],
  ["phantom", "spooky"],
  ["play", "play"],
  ["poison", "stinky"],
  ["powder", "dust"],
  ["power", "power"],
  ["protect", "shield"],
  ["psy", "brain"],
  ["psychic", "brain"],
  ["pulse", "pulse"],
  ["punch", "bonk"],
  ["quake", "shake"],
  ["quick", "fast"],
  ["rage", "mad"],
  ["rapid", "zoom"],
  ["razor", "slicey"],
  ["recover", "reset"],
  ["reflect", "mirror"],
  ["rest", "nap"],
  ["rock", "rock"],
  ["roost", "bird sit"],
  ["sand", "pocket sand"],
  ["scratch", "scritch"],
  ["seed", "seed"],
  ["shadow", "spooky"],
  ["shield", "shield"],
  ["shock", "buzz"],
  ["shot", "shot"],
  ["slash", "slice"],
  ["slam", "bonk"],
  ["sleep", "nap"],
  ["sludge", "gunk"],
  ["smash", "smash"],
  ["smoke", "smoke"],
  ["smokescreen", "smoke spam"],
  ["snarl", "edge bark"],
  ["snow", "snow"],
  ["solar", "sun"],
  ["sonic", "loud"],
  ["spike", "spike"],
  ["spin", "spin"],
  ["spirit", "ghost"],
  ["splash", "wet flop"],
  ["storm", "storm"],
  ["strength", "gym bro"],
  ["string", "sticky string"],
  ["strike", "bonk"],
  ["surf", "wave ride"],
  ["sword", "sword"],
  ["tail", "tail"],
  ["tackle", "bonk"],
  ["teleport", "blink"],
  ["thunder", "zap"],
  ["toxic", "stinky"],
  ["trail", "trail"],
  ["transform", "morph"],
  ["trick", "troll"],
  ["triple", "triple"],
  ["vacuum", "air"],
  ["vibe", "vibe"],
  ["vine", "plant"],
  ["voice", "yap"],
  ["water", "wet"],
  ["wave", "wave"],
  ["weather", "forecast"],
  ["whip", "whap"],
  ["whirl", "spin"],
  ["wind", "wind"],
  ["wing", "wing"],
  ["wisp", "lighter"],
  ["wood", "wood"],
]);

const FALLBACK_PREFIXES = ["Turbo", "Mega", "Giga", "Ultra", "Big", "Hyper"];
const SAMPLE_MOVE_KEYS = ["waterGun", "tackle", "quickAttack", "thunderbolt", "flamethrower", "psychic"];
const SAMPLE_TRIGGER_KEYS = ["fled", "regainedHealth", "copiedMove", "cannotUseMove", "struggle"];
const FLAVOR_SENTENCES = [
  "Certified wet behavior.",
  "Absolute grill mode.",
  "Maximum zappage.",
  "Haunted behavior detected.",
  "Brainrot levels critical.",
  "Whole lotta plant nonsense.",
  "Certified yap damage.",
  "Peak bonk energy.",
  "Certified nope tech.",
  "Maximum zoom.",
  "Wallet tech is online.",
  "Big move, bigger nonsense.",
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

function moveKeyToBaseName(key) {
  return key
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .split(/\s+/)
    .filter(Boolean)
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function brainrotifyWords(words) {
  return words.flatMap(word => {
    const lower = word.toLowerCase();
    const replacement = WORD_OVERRIDES.get(lower);
    if (replacement) {
      return replacement.split(/\s+/);
    }
    return [word];
  });
}

function brainrotifyMoveName(key, originalName) {
  if (EXACT_OVERRIDES[key]) {
    return EXACT_OVERRIDES[key];
  }

  const originalWords = normalizeWords(originalName);
  const replacedWords = brainrotifyWords(originalWords);
  let result = toTitleCase(replacedWords.join(" ").replace(/\s+/g, " ").trim());
  const normalizedOriginal = toTitleCase(originalWords.join(" "));

  if (!result || result.toLowerCase() === normalizedOriginal.toLowerCase()) {
    const prefix = FALLBACK_PREFIXES[hashString(key) % FALLBACK_PREFIXES.length];
    result = `${prefix} ${normalizedOriginal}`;
  }

  return result
    .replace(/\bWet Wet Wet\b/g, "Wet Wet")
    .replace(/\bBonk Bonk\b/g, "Bonk Bonk")
    .replace(/\bZap Zap Zap\b/g, "Zap Zap")
    .replace(/\bMoon Moon\b/g, "Moon Boom");
}

function pickMoveFlavor(name, key) {
  const tokens = new Set(normalizeWords(`${moveKeyToBaseName(key)} ${name}`).map(token => token.toLowerCase()));

  if (["flame", "fire", "ember", "torch", "heat", "burn", "hot"].some(token => tokens.has(token))) {
    return "Absolute grill mode.";
  }
  if (["wet", "water", "bubble", "aqua", "hydro", "surf"].some(token => tokens.has(token))) {
    return "Certified wet behavior.";
  }
  if (["zap", "thunder", "shock", "volt", "electro"].some(token => tokens.has(token))) {
    return "Maximum zappage.";
  }
  if (["spooky", "shadow", "ghost", "night", "curse", "doom"].some(token => tokens.has(token))) {
    return "Haunted behavior detected.";
  }
  if (["brain", "mind", "psy", "tele", "confuse", "trick"].some(token => tokens.has(token))) {
    return "Brainrot levels critical.";
  }
  if (["seed", "leaf", "vine", "plant", "petal", "spore"].some(token => tokens.has(token))) {
    return "Whole lotta plant nonsense.";
  }
  if (["song", "voice", "buzz", "loud", "bell", "sound"].some(token => tokens.has(token))) {
    return "Certified yap damage.";
  }
  if (
    ["bonk", "kick", "chop", "claw", "slash", "punch", "drill", "whap", "yeet", "smash", "bash", "mitt", "horn"].some(
      token => tokens.has(token),
    )
  ) {
    return "Peak bonk energy.";
  }
  if (["shield", "protect", "guard", "wall"].some(token => tokens.has(token))) {
    return "Certified nope tech.";
  }
  if (["zoom", "fast", "quick"].some(token => tokens.has(token))) {
    return "Maximum zoom.";
  }
  if (["money", "pay", "coin", "rain"].some(token => tokens.has(token))) {
    return "Wallet tech is online.";
  }
  return "Big move, bigger nonsense.";
}

function brainrotifyMoveEffect(effect, name, key) {
  const flavor = pickMoveFlavor(name, key);
  let base = effect.trim();

  let didTrimFlavor = true;
  while (didTrimFlavor) {
    didTrimFlavor = false;
    for (const candidate of FLAVOR_SENTENCES) {
      if (base.endsWith(` ${candidate}`)) {
        base = base.slice(0, -` ${candidate}`.length).trim();
        didTrimFlavor = true;
      }
    }
  }
  if (!base) {
    return flavor;
  }

  base = base
    .replace(/opposing Pokémon/gi, "the other side")
    .replace(/opposing Mogger Mon/gi, "the other side")
    .replace(/\bPokémon\b/g, "Mogger Mon")
    .replace(/\bpokémon\b/g, "Mogger Mon")
    .replace(/\bPokemon\b/g, "Mogger Mon")
    .replace(/\bpokemon\b/g, "Mogger Mon")
    .replace(/may also/gi, "can also")
    .replace(/inflict damage/gi, "deal damage")
    .replace(/([a-z’]) This move/g, "$1 this move");

  return `${base} ${flavor}`;
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function brainrotifyMoveTriggerText(text, moveNamesByKey) {
  let output = text;

  const literalMoveReplacements = [
    ["Doom Desire", moveNamesByKey.doomDesire],
    ["Healing Wish", moveNamesByKey.healingWish],
    ["Nature Power", moveNamesByKey.naturePower],
    ["Safeguard", moveNamesByKey.safeguard],
  ].filter(([, replacement]) => replacement);

  for (const [literal, replacement] of literalMoveReplacements) {
    output = output.replace(new RegExp(escapeRegExp(literal), "g"), replacement);
  }

  const replacements = [
    [/was damaged by the recoil!/g, "caught recoil hands!"],
    [/cut its own HP to power up its move!/g, "spent its own HP for extra sauce!"],
    [/absorbed electricity!/g, "ate the zap!"],
    [/regained\s*health!/g, "got the HP back!"],
    [/fled!/g, "bailed out!"],
    [/can’t be switched out!/g, "is hard stuck in here!"],
    [/whipped\s*up a whirlwind!/g, "started a whole wind mess!"],
    [/flew\s*up high!/g, "went way up there!"],
    [/absorbed light!/g, "started charging the sun!"],
    [/burrowed its way under the ground!/g, "went full dirt mode!"],
    [/became cloaked in a harsh light!/g, "went full glow mode!"],
    [/is\s*tightening its focus!/g, "is locking in!"],
    [/lost its focus and couldn’t move!/g, "lost the plot and froze up!"],
    [/vanished\s*instantly!/g, "vanished on sight!"],
    [/is absorbing power!/g, "is charging up like crazy!"],
    [/burned itself out!/g, "cooked itself too hard!"],
    [/used up all its electricity!/g, "spent every last zap!"],
    [/took\s*the {{moveName}} attack!/g, "tanked the {{moveName}} hit!"],
    [/cut its own HP\s*and maximized its {{statName}}!/g, "sold its own HP to max out {{statName}}!"],
    [/copied\s*{{targetName}}’s stat changes!/g, "stole {{targetName}}'s stat sauce!"],
    [/took aim\s*at {{targetName}}!/g, "lined up {{targetName}}!"],
    [/copied\s*{{moveName}}!/g, "jacked {{moveName}}!"],
    [/sketched\s*{{moveName}}!/g, "doodled {{moveName}} into the moveset!"],
    [/cannot use {{moveName}}!/g, "cannot click {{moveName}}!"],
    [/slept and restored its HP!/g, "took a nap and got the HP back!"],
    [/already\s*has a substitute!/g, "already has the decoy up!"],
    [/does not have enough HP\s*left to make a substitute!/g, "does not have the HP to put up a decoy!"],
    [/was revived!/g, "is back in the fight!"],
    [/has no moves left that it can use!/g, "is out of buttons to click!"],
    [/The two moves have become one!\s*It’s a combined move!/g, "The two moves locked in together! Combo tech!"],
    [/is preparing to tell a chillingly bad joke!/g, "is winding up the worst joke ever!"],
    [/fell straight down!/g, "got dropped instantly!"],
  ];

  for (const [pattern, replacement] of replacements) {
    output = output.replace(pattern, replacement);
  }

  output = output
    .replace(/\bHyper Hyper Healing Wish\b/g, "Hyper Heal Wish")
    .replace(/\bHyper Healing Wish\b/g, "Hyper Heal Wish")
    .replace(/\bHyper Hyper Heal Wish\b/g, "Hyper Heal Wish")
    .replace(/\bBig Team Nope Field\b/g, "Team Nope Field")
    .replace(/\bGiga Nature Sauce\b/g, "Nature Sauce");

  return output;
}

async function loadJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, "utf8"));
}

async function writeJson(filePath, value) {
  await fs.writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`);
}

async function main() {
  const englishMoves = await loadJson(ENGLISH_MOVE_FILE);
  const englishMoveTriggers = await loadJson(ENGLISH_MOVE_TRIGGER_FILE);
  const localeEntries = await fs.readdir(LOCALES_DIR, { withFileTypes: true });
  const moveNamesByKey = Object.fromEntries(
    Object.keys(englishMoves).map(moveKey => [moveKey, brainrotifyMoveName(moveKey, moveKeyToBaseName(moveKey))]),
  );

  let updatedMoveFiles = 0;
  let updatedTriggerFiles = 0;

  for (const localeEntry of localeEntries) {
    if (!localeEntry.isDirectory()) {
      continue;
    }

    const localeMoveFile = path.join(LOCALES_DIR, localeEntry.name, "move.json");
    const localeTriggerFile = path.join(LOCALES_DIR, localeEntry.name, "move-trigger.json");

    try {
      await fs.access(localeMoveFile);
      const localeMoves = await loadJson(localeMoveFile);
      const rewrittenMoves = {};

      for (const [moveKey, englishEntry] of Object.entries(englishMoves)) {
        const localeEntryValue = localeMoves[moveKey] ?? {};
        const brainrotName = moveNamesByKey[moveKey];
        rewrittenMoves[moveKey] = {
          ...localeEntryValue,
          name: brainrotName,
          effect: brainrotifyMoveEffect(englishEntry.effect ?? "", brainrotName, moveKey),
        };
      }

      await writeJson(localeMoveFile, rewrittenMoves);
      updatedMoveFiles += 1;
    } catch {
      // Ignore locales without move.json
    }

    try {
      await fs.access(localeTriggerFile);
      const rewrittenTriggers = {};
      for (const [triggerKey, englishText] of Object.entries(englishMoveTriggers)) {
        rewrittenTriggers[triggerKey] = brainrotifyMoveTriggerText(String(englishText), moveNamesByKey);
      }
      await writeJson(localeTriggerFile, rewrittenTriggers);
      updatedTriggerFiles += 1;
    } catch {
      // Ignore locales without move-trigger.json
    }
  }

  console.log(`Updated brainrot move names and descriptions in ${updatedMoveFiles} locale files.`);
  console.log(`Updated brainrot move-trigger text in ${updatedTriggerFiles} locale files.`);

  for (const sampleKey of SAMPLE_MOVE_KEYS) {
    const moveName = moveNamesByKey[sampleKey];
    const effect = brainrotifyMoveEffect(englishMoves[sampleKey]?.effect ?? "", moveName, sampleKey);
    console.log(`${moveKeyToBaseName(sampleKey)} -> ${moveName} :: ${effect}`);
  }

  for (const triggerKey of SAMPLE_TRIGGER_KEYS) {
    console.log(
      `${triggerKey} -> ${brainrotifyMoveTriggerText(String(englishMoveTriggers[triggerKey]), moveNamesByKey)}`,
    );
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});

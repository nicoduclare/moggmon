import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const EN_LOCALES_DIR = path.join(ROOT, "locales", "en");

const GENERIC_EXCLUDES = new Set(["bgm-name.json", "move-trigger.json", "move.json", "splash-texts.json"]);

const GENERIC_REPLACEMENTS = [
  [/PokéRogue/g, "Mogger Mon"],
  [/PokeRogue/g, "Mogger Mon"],
  [/pokerogue\.net/gi, "moggermon.gg"],
  [/Poké Ball/g, "Cryotank"],
  [/Poke Ball/g, "Cryotank"],
  [/Pokeball/g, "Cryotank"],
  [/Pokémon/g, "Mogger Mon"],
  [/Pokemon/g, "Mogger Mon"],
];

const MUSTACHE_PATTERN = /{{[^}]+}}/g;

async function* walkJsonFiles(dirPath) {
  const entries = await fs.readdir(dirPath, { withFileTypes: true });

  for (const entry of entries) {
    const entryPath = path.join(dirPath, entry.name);
    if (entry.isDirectory()) {
      yield* walkJsonFiles(entryPath);
      continue;
    }

    if (entry.isFile() && entry.name.endsWith(".json")) {
      yield entryPath;
    }
  }
}

function normalizePlaceholderNames(value) {
  return value.replace(MUSTACHE_PATTERN, placeholder =>
    placeholder.replace(/Mogger Mon/g, "Pokemon").replace(/mogmon/g, "pokemon"),
  );
}

function replaceTerms(value) {
  const placeholders = [];
  let output = normalizePlaceholderNames(value).replace(MUSTACHE_PATTERN, placeholder => {
    const index = placeholders.push(placeholder) - 1;
    return `__MOGMON_PLACEHOLDER_${index}__`;
  });

  for (const [pattern, replacement] of GENERIC_REPLACEMENTS) {
    output = output.replace(pattern, replacement);
  }

  return output.replace(/__MOGMON_PLACEHOLDER_(\d+)__/g, (_, index) => placeholders[Number(index)] ?? "");
}

function transformStrings(value) {
  if (typeof value === "string") {
    return replaceTerms(value);
  }
  if (Array.isArray(value)) {
    return value.map(transformStrings);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, transformStrings(child)]));
  }
  return value;
}

async function loadJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, "utf8"));
}

async function writeJson(filePath, value) {
  await fs.writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`);
}

async function rebrandGenericEnglishFiles() {
  let updatedCount = 0;

  for await (const filePath of walkJsonFiles(EN_LOCALES_DIR)) {
    if (GENERIC_EXCLUDES.has(path.basename(filePath))) {
      continue;
    }

    const json = await loadJson(filePath);
    await writeJson(filePath, transformStrings(json));
    updatedCount += 1;
  }

  return updatedCount;
}

async function rebrandTutorial() {
  const filePath = path.join(EN_LOCALES_DIR, "tutorial.json");
  const tutorial = await loadJson(filePath);

  tutorial.intro =
    'Welcome to Mogger Mon! This is a battle-focused monster roguelite prototype.$This build still contains inherited placeholder content and temporary assets while the full Mogger Mon swap is underway.$The game is a work in progress, but fully playable.\nFor bug reports, please use the Discord community.$If the game runs slowly, please ensure "Hardware Acceleration" is turned on in your browser settings.';

  tutorial.starterSelect =
    "From this screen, you can select your starters by pressing\nZ or the Space bar. These are your initial party members.$Each starter has a value. Your party can have up to\n6 members as long as the total does not exceed 10.$You can also select gender, ability, and form depending on\nthe variants you've caught or hatched.$The IVs for a species are also the best of every one you've\ncaught or hatched, so try to build up a deep Mogger Mon bench!";

  tutorial.statChange =
    "Stat changes persist across battles as long as your Mogger Mon aren't recalled.$Your Mogger Mon are recalled before a trainer battle and before entering a new biome.$You can view the stat changes for any Mogger Mon on the field by holding C or Shift.$You can also view the moveset for an enemy Mogger Mon by holding V.$This only reveals moves that you've seen the enemy use this battle.";

  tutorial.selectItem =
    "After every battle, you are given a choice of 3 random items.\nYou may only pick one.$These range from consumables, to Mogger Mon held items, to passive permanent items.$Most non-consumable item effects will stack in various ways.$Some items will only show up if they can be used, such as evolution items.$You can also transfer held items between Mogger Mon using the transfer option.$The transfer option will appear in the bottom right once you have obtained a held item.$You may purchase consumable items with money, and a larger variety will be available the further you get.$Be sure to buy these before you pick your random item, as it will progress to the next battle once you do.";

  tutorial.eggGacha =
    "From this screen, you can redeem your vouchers for\nMogger Mon Eggs.$Eggs inch closer to hatching after every battle. Rarer Eggs take longer to hatch.$Hatched Mogger Mon won't be added to your party, they will\nbe added to your starter pool.$Mogger Mon hatched from Eggs generally have better IVs than\nwild Mogger Mon.$Some Mogger Mon can only be obtained from Eggs.$There are 3 different machines with different bonuses, so pick the one that suits you best.";

  await writeJson(filePath, tutorial);
}

async function rebrandSplashTexts() {
  const filePath = path.join(EN_LOCALES_DIR, "splash-texts.json");
  const splash = await loadJson(filePath);

  Object.assign(splash, {
    underratedPokemon: "Underrated Mogger Mon: {{pokemonName}}!",
    pokemonRiskAndPokemonRain: "Mogger Mon Risk and Mogger Mon Rain!",
    dontTalkAboutThePokemonIncident: "Don't Talk About the {{pokemonName}} Incident!",
    alsoTryPokerogueWait: "Also Try Mogger Mon! Wait...",
    pokerogueMorse: "-- --- --. --. . .-. / -- --- -.",
    onlyOnPokerogueNet: "Only on Mogger Mon!",
    yourPokemonOnlyGoToLevelOneHundred: "Your Mogger Mon Only Go To Level 100?",
    aWildPokemonAppeared: "A Wild {{pokemonName}} Appeared!",
    doNotTrespass: "Do not trespass while playing Mogger Mon.",
    askYourDoctor: "Ask Your Doctor if Mogger Mon is Right For You.",
  });

  splash.aprilFools.removedPokemon = "Removed {{pokemonName}}!";
  splash.aprilFools.alsoTryPokerogueTwo = "Also Try Mogger Mon 2!";
  splash.aprilFools.watchOutForShadowPokemon = "Watch Out For Shadow Mogger Mon!";
  splash.aprilFools.onlyOnPokerogueNetAgain = "ONLY ON MOGGER MON!";
  splash.aprilFools.rokePogue = "Mogger Mon!";

  await writeJson(filePath, splash);
}

async function rebrandBgmNames() {
  const filePath = path.join(EN_LOCALES_DIR, "bgm-name.json");
  const bgmNames = await loadJson(filePath);

  bgmNames.title = "Firel - Mogger Mon";

  await writeJson(filePath, bgmNames);
}

async function main() {
  const updatedGenericFiles = await rebrandGenericEnglishFiles();
  await rebrandTutorial();
  await rebrandSplashTexts();
  await rebrandBgmNames();

  console.log(`Rebranded English UI copy in ${updatedGenericFiles} generic locale files.`);
  console.log("Updated tutorial, splash texts, and BGM title overrides for Mogger Mon branding.");
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});

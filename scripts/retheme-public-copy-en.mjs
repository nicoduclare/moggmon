import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const LOCALES_EN_DIR = path.join(ROOT, "locales", "en");

const PLACEHOLDER_PATTERN = /{{[^}]+}}/g;

const PHRASE_REPLACEMENTS = [
  [/\bPokedex\b/g, "Archive"],
  [/\bPok[eé]balls\b/g, "Cryotanks"],
  [/\bPok[eé]ball\b/g, "Cryotank"],
  [/\bPokemon\b/g, "Mogger Mon"],
  [/\bpokemon\b/g, "Mogger Mon"],
  [/\bStarters\b/g, "Recruits"],
  [/\bstarters\b/g, "recruits"],
  [/\bStarter\b/g, "Recruit"],
  [/\bstarter\b/g, "recruit"],
  [/\bAbilities\b/g, "Traits"],
  [/\bAbility\b/g, "Trait"],
  [/\bMoves\b/g, "Techniques"],
  [/\bMove\b/g, "Technique"],
  [/\bItems\b/g, "Relics"],
  [/\bItem\b/g, "Relic"],
  [/\bSnacks\b/g, "Zaza"],
  [/\bsnacks\b/g, "zaza"],
  [/\bSnack\b/g, "Zaza"],
  [/\bsnack\b/g, "zaza"],
  [/\bBerries\b/g, "Zaza"],
  [/\bberries\b/g, "zaza"],
  [/\bBerry\b/g, "Zaza"],
  [/\bberry\b/g, "zaza"],
  [/\bEgg Moves\b/g, "Signal Techs"],
  [/\bEgg Move\b/g, "Signal Tech"],
  [/\begg moves\b/g, "signal techs"],
  [/\begg move\b/g, "signal tech"],
  [/\bTM Moves\b/g, "BrainDances"],
  [/\bTM Move\b/g, "BrainDance"],
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
  [/\bfrom a braindance\b/g, "from a BrainDance disc"],
  [/\bany braindances\b/g, "any BrainDance discs"],
  [/\bCryptanks\b/g, "Cryotanks"],
  [/\bCryptank\b/g, "Cryotank"],
  [/\bcryptanks\b/g, "cryotanks"],
  [/\bcryptank\b/g, "cryotank"],
  [/\bHidden Ability\b/g, "Hidden Trait"],
  [/\bShiny\b/g, "Glitch"],
  [/\bshiny\b/g, "glitch"],
  [/\bheld items\b/g, "held relics"],
  [/\bheld item\b/g, "held relic"],
  [/\ban Ability\b/g, "a Trait"],
  [/\bAn Ability\b/g, "A Trait"],
  [/\ban ability\b/g, "a trait"],
  [/\bAn ability\b/g, "A trait"],
  [/\ban Item\b/g, "a Relic"],
  [/\bAn Item\b/g, "A Relic"],
  [/\ban item\b/g, "a relic"],
  [/\bAn item\b/g, "A relic"],
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

function rethemeString(value) {
  const { protectedValue, placeholders } = protectPlaceholders(value);
  let next = protectedValue;
  for (const [pattern, replacement] of PHRASE_REPLACEMENTS) {
    next = next.replace(pattern, replacement);
  }
  return restorePlaceholders(next, placeholders);
}

function transformNode(node) {
  if (typeof node === "string") {
    return rethemeString(node);
  }
  if (Array.isArray(node)) {
    return node.map(item => transformNode(item));
  }
  if (node && typeof node === "object") {
    return Object.fromEntries(Object.entries(node).map(([key, value]) => [key, transformNode(value)]));
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

let changedFiles = 0;
for await (const filePath of walkJsonFiles(LOCALES_EN_DIR)) {
  const originalText = await fs.readFile(filePath, "utf8");
  const parsed = JSON.parse(originalText);
  const transformed = transformNode(parsed);
  const nextText = `${JSON.stringify(transformed, null, 2)}\n`;
  if (nextText !== originalText) {
    await fs.writeFile(filePath, nextText, "utf8");
    changedFiles += 1;
  }
}

console.log(`Rethemed public English locale copy in ${changedFiles} files.`);

import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const OUTPUT_DIR = path.join(ROOT, "scripts", "data");
const OUTPUT_FILE = path.join(OUTPUT_DIR, "brainrot-trait-megalist.json");
const API_URL =
  "https://stealabrainrot.fandom.com/api.php?action=query&list=categorymembers&cmtitle=Category:Brainrots&cmlimit=max&format=json";

const STOP_WORDS = new Set([
  "a",
  "admin",
  "an",
  "and",
  "brainrot",
  "brainrots",
  "block",
  "de",
  "del",
  "della",
  "delle",
  "di",
  "el",
  "family",
  "god",
  "la",
  "le",
  "lo",
  "los",
  "of",
  "the",
  "trader",
]);

const CANONICAL_PATTERNS = [
  [/tralal/i, "tralala"],
  [/sahur/i, "sahur"],
  [/pata(pim|pum)/i, "patapim"],
  [/cappucc/i, "cappu"],
  [/assass/i, "assa"],
  [/bomb/i, "bomba"],
  [/brr/i, "brr"],
  [/bici/i, "bici"],
  [/croc/i, "croco"],
  [/dolph/i, "dolphi"],
  [/beluga/i, "beluga"],
  [/bunny/i, "bunny"],
  [/egg/i, "eggi"],
  [/goat/i, "goat"],
  [/pegasus/i, "pegasi"],
  [/dragon/i, "drago"],
  [/camelo|camel/i, "camelo"],
  [/frigo|frost|ice/i, "frigo"],
  [/fuego|fire|flame|lava/i, "rizz"],
  [/volt|electr|lightn/i, "zappi"],
  [/storm/i, "stormi"],
  [/shark/i, "sharki"],
  [/fish/i, "fishi"],
  [/octop/i, "octo"],
  [/panda/i, "panda"],
  [/hipopot|hippo/i, "hippo"],
  [/rabbit|hare/i, "bunny"],
  [/wolf|dog|cachorr/i, "bau"],
  [/cat|gatto/i, "gatti"],
  [/bird|buho|owl|eagle|pegasus/i, "voli"],
  [/spider|arachn/i, "spidi"],
  [/banana/i, "banana"],
  [/avoca/i, "avoca"],
  [/carrot/i, "carro"],
  [/berry/i, "berry"],
  [/melon/i, "melon"],
  [/bambu/i, "bambu"],
  [/cacto|cactus/i, "cacto"],
  [/coffee|boba/i, "boba"],
  [/choco|caramel/i, "sweeti"],
  [/taco|burrito|fry/i, "taco"],
  [/brain|intel|mind/i, "braini"],
  [/ghost|spirit|shadow/i, "boo"],
  [/dark|night|noelo/i, "ombra"],
  [/gold|lucky/i, "lucki"],
  [/nuclear|blackhole|celestial|astro|mars|moon|luna|star/i, "cosmi"],
  [/mecha|tech|phone|celular|arcad/i, "techi"],
  [/royal|king|queen|capitano|captain/i, "boss"],
];

const TRAIT_RULES = [
  { trait: "water", patterns: [/aqua|boat|camelo|dolph|fishi|mar|moby|octo|sea|shark|trelalala|water|whale/i] },
  { trait: "fire", patterns: [/bomb|bruci|fuego|lava|rizz|volcano/i] },
  { trait: "electric", patterns: [/brr|storm|volt|zapp/i] },
  { trait: "plant", patterns: [/avoca|banana|bambu|berry|cacto|carro|corn|flower|leaf|melon|plant|seed|tree|weed/i] },
  { trait: "reptile", patterns: [/croco|drago|lizard|rept|sahur|snake/i] },
  {
    trait: "mammal",
    patterns: [/antelop|bau|bear|bison|bunny|camel|dog|fox|gatti|goat|hippo|monkey|panda|rabbit|wolf/i],
  },
  { trait: "bird", patterns: [/bird|buho|eagle|pegasi|voli|wing/i] },
  { trait: "bug", patterns: [/arachn|bee|bug|octo|spidi|spider/i] },
  { trait: "spooky", patterns: [/boo|ghost|ombra|shadow|skull|spirit/i] },
  { trait: "psychic", patterns: [/braini|mind|psy|tele/i] },
  { trait: "metal", patterns: [/armor|iron|metal|nuclear|robot|steel|tech/i] },
  { trait: "cosmic", patterns: [/astro|blackhole|celestial|cosmi|luna|mars|moon|star/i] },
  { trait: "food", patterns: [/avoca|banana|berry|boba|bread|cappu|carro|choco|coffee|fry|melon|sweeti|taco/i] },
  { trait: "cute", patterns: [/baby|bunny|cut|eggi|loli|mini|panda|peppermint/i] },
  { trait: "fight", patterns: [/assa|bandit|boss|brawl|gangster|killer|war/i] },
  { trait: "speed", patterns: [/dash|fast|spin|zoom/i] },
  { trait: "music", patterns: [/baller|bopp|dance|lolo|song/i] },
];

function unique(values) {
  return [...new Set(values)];
}

function asciiFold(value) {
  return value.normalize("NFKD").replace(/\p{Diacritic}/gu, "");
}

function splitWords(title) {
  return asciiFold(title)
    .replace(/[/()'’]/g, " ")
    .split(/[^a-zA-Z0-9]+/)
    .map(part => part.trim().toLowerCase())
    .filter(Boolean)
    .filter(part => !STOP_WORDS.has(part));
}

function fallbackAtom(token) {
  return token
    .replace(
      /(issimi|issimo|issima|azioni|zione|zioni|menti|mento|ette|etti|etto|etta|ette|ini|ino|ina|oni|one|ona|iti|ito|ita|eri|ero|era|ali|ale|oso|osa|ici|ico|ica|ucci|uccio|uccia)$/i,
      "",
    )
    .replace(/(.)\1{2,}/g, "$1$1")
    .slice(0, 6);
}

function normalizeAtom(token) {
  if (!token) {
    return null;
  }

  if (/^\d+$/.test(token) || /^(\d+x?)+\d*$/i.test(token)) {
    return null;
  }

  for (const [pattern, replacement] of CANONICAL_PATTERNS) {
    if (pattern.test(token)) {
      return replacement;
    }
  }

  const stem = fallbackAtom(token);
  if (stem.length < 3 || STOP_WORDS.has(stem)) {
    return null;
  }

  return stem;
}

function inferTraits(title, words, atoms) {
  const haystack = `${asciiFold(title).toLowerCase()} ${words.join(" ")} ${atoms.join(" ")}`;
  const traits = TRAIT_RULES.filter(rule => rule.patterns.some(pattern => pattern.test(haystack))).map(
    rule => rule.trait,
  );

  return traits.length > 0 ? traits : ["wild"];
}

async function fetchBrainrotTitles() {
  const titles = [];
  let nextUrl = API_URL;

  while (nextUrl) {
    const response = await fetch(nextUrl, {
      headers: {
        "user-agent": "mogmon-brainrot-builder/1.0",
      },
    });

    if (!response.ok) {
      throw new Error(`Wiki request failed: ${response.status} ${response.statusText}`);
    }

    const payload = await response.json();
    const members = payload.query?.categorymembers ?? [];

    for (const member of members) {
      if (typeof member.title === "string" && member.title.trim()) {
        titles.push(member.title.trim());
      }
    }

    if (payload.continue?.cmcontinue) {
      nextUrl = `${API_URL}&cmcontinue=${encodeURIComponent(payload.continue.cmcontinue)}`;
    } else {
      nextUrl = null;
    }
  }

  return unique(titles).sort((left, right) => left.localeCompare(right));
}

function buildMegalist(titles) {
  const brainrots = titles.map(title => {
    const words = splitWords(title);
    const atoms = unique(words.map(normalizeAtom).filter(Boolean));
    const traits = inferTraits(title, words, atoms);

    return {
      title,
      slug: title
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, ""),
      words,
      atoms,
      traits,
    };
  });

  const allAtoms = unique(brainrots.flatMap(entry => entry.atoms)).sort((left, right) => left.localeCompare(right));
  const atomsByTrait = Object.fromEntries(
    unique(brainrots.flatMap(entry => entry.traits))
      .sort((left, right) => left.localeCompare(right))
      .map(trait => [
        trait,
        allAtoms.filter(atom => brainrots.some(entry => entry.traits.includes(trait) && entry.atoms.includes(atom))),
      ]),
  );

  return {
    fetchedAt: new Date().toISOString(),
    source: {
      wiki: "https://stealabrainrot.fandom.com/wiki/Steal_a_Brainrot_Wiki",
      api: API_URL,
      totalPages: titles.length,
    },
    allAtoms,
    atomsByTrait,
    brainrots,
  };
}

async function main() {
  const titles = await fetchBrainrotTitles();
  const megalist = buildMegalist(titles);

  await fs.mkdir(OUTPUT_DIR, { recursive: true });
  await fs.writeFile(OUTPUT_FILE, `${JSON.stringify(megalist, null, 2)}\n`);

  console.log(`Wrote ${megalist.brainrots.length} brainrots and ${megalist.allAtoms.length} atoms to ${OUTPUT_FILE}`);
  console.log(`Traits: ${Object.keys(megalist.atomsByTrait).join(", ")}`);
  console.log(`Sample atoms: ${megalist.allAtoms.slice(0, 24).join(", ")}`);
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});

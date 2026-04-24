import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const LOCALES_DIR = path.join(ROOT, "locales");
const ENGLISH_POKEMON_FILE = path.join(LOCALES_DIR, "en", "pokemon.json");
const MEGALIST_FILE = path.join(ROOT, "scripts", "data", "brainrot-trait-megalist.json");
const OUTPUT_DIR = path.join(ROOT, "output", "private-generation-prompts", "brainrot-wiki");
const IMAGES_DIR = path.join(OUTPUT_DIR, "images");
const IMAGE_INDEX_FILE = path.join(OUTPUT_DIR, "brainrot-image-index.json");
const GEN1_REFERENCE_FILE = path.join(OUTPUT_DIR, "gen1-reference.json");
const GEN1_REFERENCE_TSV_FILE = path.join(OUTPUT_DIR, "gen1-reference.tsv");
const API_URL =
  "https://stealabrainrot.fandom.com/api.php?action=query&generator=categorymembers&gcmtitle=Category:Brainrots&gcmlimit=max&prop=pageimages&piprop=original&format=json";

const PAGE_SIZE = 151;
const MATCHES_PER_SPECIES = 3;
const DOWNLOAD_MATCHES_PER_SPECIES = 3;
const USER_AGENT = "Mozilla/5.0 (compatible; MoggerMonBrainrotFetcher/1.0; +https://github.com/auramaxx/mogger-mon)";

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

const STAGE_TOKENS = new Set(["boss", "final", "max", "omega", "plus", "prime", "ultra"]);

const CANONICAL_PATTERNS = [
  [/tr[ae]lal/i, "tralala"],
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
    .slice(0, 8);
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

function isReferenceBrainrot(entry) {
  if (!entry) {
    return false;
  }

  if (entry.title.includes(":")) {
    return false;
  }

  if (/^\d/.test(entry.title)) {
    return false;
  }

  if (entry.atoms.length === 0) {
    return false;
  }

  return !/^(brainrot god|brainrot trader|brainrots|w or l)$/i.test(entry.title);
}

function inferExtension(imageUrl, contentType) {
  const pathname = imageUrl ? new URL(imageUrl).pathname : "";
  const lastSegment = pathname.split("/").pop() || "";
  const extension = path.extname(lastSegment).toLowerCase();

  if (extension) {
    return extension;
  }

  const normalizedType = contentType?.toLowerCase() || "";
  if (normalizedType.includes("png")) {
    return ".png";
  }
  if (normalizedType.includes("jpeg") || normalizedType.includes("jpg")) {
    return ".jpg";
  }
  if (normalizedType.includes("webp")) {
    return ".webp";
  }
  if (normalizedType.includes("gif")) {
    return ".gif";
  }

  return ".img";
}

async function fetchWikiImageIndex() {
  const pages = [];
  let nextUrl = API_URL;

  while (nextUrl) {
    const response = await fetch(nextUrl, {
      headers: {
        "user-agent": USER_AGENT,
      },
    });

    if (!response.ok) {
      throw new Error(`Wiki image request failed: ${response.status} ${response.statusText}`);
    }

    const payload = await response.json();
    const queryPages = Object.values(payload.query?.pages ?? {});

    for (const page of queryPages) {
      if (!page?.title) {
        continue;
      }

      pages.push({
        title: page.title,
        imageUrl: page.original?.source ?? null,
        imageWidth: page.original?.width ?? null,
        imageHeight: page.original?.height ?? null,
      });
    }

    if (payload.continue?.gcmcontinue) {
      nextUrl = `${API_URL}&gcmcontinue=${encodeURIComponent(payload.continue.gcmcontinue)}`;
    } else {
      nextUrl = null;
    }
  }

  return unique(pages.map(page => page.title))
    .sort((left, right) => left.localeCompare(right))
    .map(title => pages.find(page => page.title === title));
}

function buildImageIndex(megalist, fetchedPages) {
  const pageMap = new Map(fetchedPages.map(page => [page.title, page]));

  return megalist.brainrots.map(brainrot => {
    const page = pageMap.get(brainrot.title);
    return {
      ...brainrot,
      imageUrl: page?.imageUrl ?? null,
      imageWidth: page?.imageWidth ?? null,
      imageHeight: page?.imageHeight ?? null,
    };
  });
}

function extractNameTokens(name) {
  const rawWords = splitWords(name);
  const conceptWords = rawWords.filter(word => !STAGE_TOKENS.has(word));
  const atoms = unique(conceptWords.map(normalizeAtom).filter(Boolean)).filter(atom => !STAGE_TOKENS.has(atom));
  const phrase = atoms.join(" ");

  return {
    words: rawWords,
    conceptWords,
    atoms,
    phrase,
  };
}

function scoreBrainrotMatch(nameTokens, brainrot) {
  const titleHaystack = asciiFold(brainrot.title).toLowerCase();
  const wordSet = new Set(brainrot.words);
  const atomSet = new Set(brainrot.atoms);
  const overlapAtoms = nameTokens.atoms.filter(atom => atomSet.has(atom));
  const overlapWords = nameTokens.conceptWords.filter(word => wordSet.has(word));

  let score = 0;

  if (overlapAtoms.length > 0) {
    score += overlapAtoms.length * 35;
  }
  if (overlapWords.length > 0) {
    score += overlapWords.length * 15;
  }
  if (nameTokens.phrase && titleHaystack.includes(nameTokens.phrase)) {
    score += 40;
  }

  for (const atom of nameTokens.atoms) {
    if (atom.length >= 3 && titleHaystack.includes(atom)) {
      score += 8;
    }
  }

  if (/family/i.test(brainrot.title)) {
    score -= 8;
  }

  return {
    score,
    overlapAtoms,
    overlapWords,
  };
}

function compareMatches(left, right) {
  const leftExtraAtoms = Math.max(0, left.entryAtomCount - left.overlapAtoms.length);
  const rightExtraAtoms = Math.max(0, right.entryAtomCount - right.overlapAtoms.length);

  return (
    right.score - left.score
    || right.overlapAtoms.length - left.overlapAtoms.length
    || right.overlapWords.length - left.overlapWords.length
    || leftExtraAtoms - rightExtraAtoms
    || left.title.split(/\s+/).length - right.title.split(/\s+/).length
    || left.title.localeCompare(right.title)
  );
}

async function downloadImage(entry) {
  if (!entry.imageUrl) {
    return null;
  }

  const response = await fetch(entry.imageUrl, {
    headers: {
      "user-agent": USER_AGENT,
    },
  });

  if (!response.ok) {
    throw new Error(`Image download failed for ${entry.title}: ${response.status} ${response.statusText}`);
  }

  const contentType = response.headers.get("content-type");
  const extension = inferExtension(entry.imageUrl, contentType);
  const outputPath = path.join(IMAGES_DIR, `${entry.slug}${extension}`);
  const bytes = Buffer.from(await response.arrayBuffer());

  await fs.writeFile(outputPath, bytes);

  return {
    relativePath: path.relative(ROOT, outputPath).replaceAll(path.sep, "/"),
    extension,
    bytes: bytes.length,
  };
}

function toTsv(rows) {
  const header = ["dex", "speciesKey", "generatedName", "matchedBrainrots", "localImages", "matchScores"];
  const lines = [header.join("\t")];

  for (const row of rows) {
    lines.push(
      [
        String(row.dex),
        row.speciesKey,
        row.generatedName,
        row.matches.map(match => match.title).join(" | "),
        row.matches.map(match => match.localImagePath || "").join(" | "),
        row.matches.map(match => String(match.score)).join(" | "),
      ]
        .map(value => value.replaceAll("\t", " "))
        .join("\t"),
    );
  }

  return `${lines.join("\n")}\n`;
}

async function main() {
  const englishPokemon = JSON.parse(await fs.readFile(ENGLISH_POKEMON_FILE, "utf8"));
  const megalist = JSON.parse(await fs.readFile(MEGALIST_FILE, "utf8"));
  const firstGenKeys = Object.keys(englishPokemon).slice(0, PAGE_SIZE);
  const fetchedPages = await fetchWikiImageIndex();
  const imageIndex = buildImageIndex(megalist, fetchedPages);
  const imageIndexMap = new Map(imageIndex.map(entry => [entry.title, entry]));
  const referenceBrainrots = imageIndex.filter(isReferenceBrainrot);
  const gen1Reference = [];
  const downloads = new Map();

  await fs.rm(OUTPUT_DIR, { recursive: true, force: true });
  await fs.mkdir(IMAGES_DIR, { recursive: true });

  for (const [index, speciesKey] of firstGenKeys.entries()) {
    const generatedName = englishPokemon[speciesKey];
    const nameTokens = extractNameTokens(generatedName);
    const matches = referenceBrainrots
      .map(entry => {
        const { score, overlapAtoms, overlapWords } = scoreBrainrotMatch(nameTokens, entry);
        return {
          title: entry.title,
          slug: entry.slug,
          score,
          entryAtomCount: entry.atoms.length,
          overlapAtoms,
          overlapWords,
        };
      })
      .filter(entry => entry.score > 0)
      .sort(compareMatches)
      .slice(0, MATCHES_PER_SPECIES);

    gen1Reference.push({
      dex: index + 1,
      speciesKey,
      generatedName,
      tokens: nameTokens,
      matches,
    });
  }

  const titlesToDownload = unique(
    gen1Reference.flatMap(row => row.matches.slice(0, DOWNLOAD_MATCHES_PER_SPECIES).map(match => match.title)),
  );

  for (const title of titlesToDownload) {
    const entry = imageIndexMap.get(title);
    if (!entry?.imageUrl) {
      continue;
    }

    try {
      downloads.set(title, await downloadImage(entry));
    } catch (error) {
      console.error(String(error));
    }
  }

  const hydratedReference = gen1Reference.map(row => ({
    ...row,
    matches: row.matches.map(match => {
      const imageEntry = imageIndexMap.get(match.title);
      const download = downloads.get(match.title);

      return {
        ...match,
        imageUrl: imageEntry?.imageUrl ?? null,
        imageWidth: imageEntry?.imageWidth ?? null,
        imageHeight: imageEntry?.imageHeight ?? null,
        localImagePath: download?.relativePath ?? null,
        localImageBytes: download?.bytes ?? null,
      };
    }),
  }));

  await fs.mkdir(OUTPUT_DIR, { recursive: true });
  await fs.writeFile(
    IMAGE_INDEX_FILE,
    `${JSON.stringify(
      {
        fetchedAt: new Date().toISOString(),
        source: {
          wiki: "https://stealabrainrot.fandom.com/wiki/Steal_a_Brainrot_Wiki",
          api: API_URL,
        },
        entries: imageIndex,
      },
      null,
      2,
    )}\n`,
  );
  await fs.writeFile(
    GEN1_REFERENCE_FILE,
    `${JSON.stringify(
      {
        generatedAt: new Date().toISOString(),
        source: {
          wiki: "https://stealabrainrot.fandom.com/wiki/Steal_a_Brainrot_Wiki",
          imageIndex: path.relative(ROOT, IMAGE_INDEX_FILE).replaceAll(path.sep, "/"),
          firstGenCount: PAGE_SIZE,
        },
        entries: hydratedReference,
      },
      null,
      2,
    )}\n`,
  );
  await fs.writeFile(GEN1_REFERENCE_TSV_FILE, toTsv(hydratedReference));

  console.log(`Wrote ${imageIndex.length} brainrot image-index entries to ${IMAGE_INDEX_FILE}`);
  console.log(`Wrote ${hydratedReference.length} first-gen references to ${GEN1_REFERENCE_FILE}`);
  console.log(`Downloaded ${downloads.size} reference images to ${IMAGES_DIR}`);
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});

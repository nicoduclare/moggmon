import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..");
const speciesEnumPath = path.join(projectRoot, "src/enums/species-id.ts");
const assetsRoot = path.join(projectRoot, "assets");
const outputPath = path.join(projectRoot, "docs/brainrot-asset-manifest.json");

const SPECIAL_DISPLAY_NAMES = new Map([
  ["FARFETCHD", "Farfetch'd"],
  ["HO_OH", "Ho-Oh"],
  ["JANGMO_O", "Jangmo-o"],
  ["HAKAMO_O", "Hakamo-o"],
  ["KOMMO_O", "Kommo-o"],
  ["MR_MIME", "Mr. Mime"],
  ["MR_RIME", "Mr. Rime"],
  ["MIME_JR", "Mime Jr."],
  ["NIDORAN_F", "Nidoran F"],
  ["NIDORAN_M", "Nidoran M"],
  ["PORYGON_Z", "Porygon-Z"],
  ["TYPE_NULL", "Type: Null"],
  ["WO_CHIEN", "Wo-Chien"],
  ["CHI_YU", "Chi-Yu"],
  ["TING_LU", "Ting-Lu"],
  ["CHIEN_PAO", "Chien-Pao"],
]);

const CURATED_SUGGESTIONS = new Map([
  ["BULBASAUR", "Broccolisaur"],
  ["IVYSAUR", "Pestosaur"],
  ["VENUSAUR", "Gigapestosaur"],
  ["CHARMANDER", "Bombardmander"],
  ["CHARMELEON", "Bombardeleon"],
  ["CHARIZARD", "Bombardragon"],
  ["SQUIRTLE", "Trelalalashark"],
  ["WARTORTLE", "Trelalalaturtle"],
  ["BLASTOISE", "Trelalalacannon"],
  ["PIKACHU", "Zapuccino"],
  ["RAICHU", "Grandzapuccino"],
  ["EEVEE", "Eevissimo"],
  ["SNORLAX", "Snorrelaxo"],
  ["MAGIKARP", "Floppaccino"],
  ["GYARADOS", "Gyaradoni"],
  ["PSYDUCK", "Brainrot Ducko"],
  ["GENGAR", "Spookeroni"],
  ["LAPRAS", "Lapragnia"],
  ["MEWTWO", "Mewtwissimo"],
  ["MEW", "Mozzarellmew"],
  ["CHIKORITA", "Chicoritooni"],
  ["CYNDAQUIL", "Cyndaqwilli"],
  ["TOTODILE", "Totodilli"],
  ["TREECKO", "Geckolini"],
  ["TORCHIC", "Chickaccino"],
  ["MUDKIP", "Mudkippo"],
  ["TURTWIG", "Turtwiggiano"],
  ["CHIMCHAR", "Chimcharoni"],
  ["PIPLUP", "Pipluppo"],
  ["SNIVY", "Snivissimo"],
  ["TEPIG", "Pepigroni"],
  ["OSHAWOTT", "Oshawhatt"],
  ["CHESPIN", "Chestpino"],
  ["FENNEKIN", "Fennecchino"],
  ["FROAKIE", "Froakissimo"],
  ["ROWLET", "Raviowli"],
  ["LITTEN", "Littenzoni"],
  ["POPPLIO", "Popplissimo"],
  ["GROOKEY", "Groovekey-o"],
  ["SCORBUNNY", "Scorbunnissimo"],
  ["SOBBLE", "Sobbollini"],
  ["SPRIGATITO", "Sprigatini"],
  ["FUECOCO", "Fuecocozza"],
  ["QUAXLY", "Quackarelli"],
  ["MIMIKYU", "Mimikyutie"],
  ["DRAGAPULT", "Dragapultissimo"],
  ["GIMMIGHOUL", "Gimmigoblin"],
  ["TINKATON", "Tinkatoni"],
  ["OGERPON", "Ogerpasta"],
]);

const FALLBACK_PREFIXES = [
  "Ballerino",
  "Braino",
  "Chonk",
  "Gobblino",
  "Mambo",
  "Rizzo",
  "Spaghetto",
  "Tralalo",
  "Zappo",
  "Zozzalo",
];

const FALLBACK_SUFFIXES = ["ccino", "doro", "ella", "etto", "issimo", "maxx", "oni", "tron", "tastic", "zillo"];

const STEM_REPLACEMENTS = [
  [/saur/gi, "saurino"],
  [/mander/gi, "mandoro"],
  [/meleon/gi, "meleono"],
  [/izard/gi, "izardo"],
  [/turtle/gi, "tortellini"],
  [/duck/gi, "ducko"],
  [/mouse/gi, "mousini"],
  [/wolf/gi, "wolfetti"],
  [/fox/gi, "foxxo"],
  [/lion/gi, "lionello"],
  [/cat/gi, "catto"],
  [/dog/gi, "doggo"],
  [/bird/gi, "birdo"],
  [/bat/gi, "battoni"],
  [/ghost/gi, "ghosto"],
  [/dragon/gi, "dragoni"],
  [/fish/gi, "fishio"],
  [/frog/gi, "froggino"],
  [/snake/gi, "serpentino"],
  [/shark/gi, "sharkissimo"],
];

const SPECIES_BUCKET_ORDER = [
  "front",
  "front_female",
  "front_shiny",
  "front_shiny_female",
  "back",
  "back_female",
  "back_shiny",
  "back_shiny_female",
  "exp_front",
  "exp_front_female",
  "exp_front_shiny",
  "exp_front_shiny_female",
  "exp_back",
  "exp_back_female",
  "exp_back_shiny",
  "variant_front",
  "variant_front_female",
  "variant_back",
  "variant_back_female",
  "variant_exp_front",
  "variant_exp_front_female",
  "variant_exp_back",
];

const ASSET_BUCKET_SPECS = [
  {
    key: "branding",
    priority: "required",
    description: "Root brand assets shown before gameplay loads or when shared as an iframe page.",
    paths: [
      "assets/logo128.png",
      "assets/logo512.png",
      "assets/manifest.webmanifest",
      "assets/service-worker.js",
      "assets/images/logo.png",
      "assets/images/logo_fake.png",
    ],
  },
  {
    key: "pokemon_front",
    priority: "required",
    description: "Main front-facing species and form battle atlases.",
    dir: "assets/images/pokemon",
  },
  {
    key: "pokemon_front_shiny",
    priority: "recommended",
    description: "Shiny front battle atlases.",
    dir: "assets/images/pokemon/shiny",
  },
  {
    key: "pokemon_front_female",
    priority: "recommended",
    description: "Female-specific front battle atlases.",
    dir: "assets/images/pokemon/female",
  },
  {
    key: "pokemon_back",
    priority: "required",
    description: "Back-facing player-side battle atlases.",
    dir: "assets/images/pokemon/back",
  },
  {
    key: "pokemon_back_shiny",
    priority: "recommended",
    description: "Shiny back battle atlases.",
    dir: "assets/images/pokemon/back/shiny",
  },
  {
    key: "pokemon_expanded_front",
    priority: "optional",
    description: "Expanded high-detail front atlases used by some encounter flows.",
    dir: "assets/images/pokemon/exp",
  },
  {
    key: "pokemon_expanded_back",
    priority: "optional",
    description: "Expanded high-detail back atlases.",
    dir: "assets/images/pokemon/exp/back",
  },
  {
    key: "pokemon_variant_front",
    priority: "required",
    description: "Special regional, mega, gigantamax, and other variant front atlases.",
    dir: "assets/images/pokemon/variant",
  },
  {
    key: "pokemon_variant_back",
    priority: "required",
    description: "Variant back atlases.",
    dir: "assets/images/pokemon/variant/back",
  },
  {
    key: "pokemon_icon_sources",
    priority: "required",
    description: "Per-species icon source directories used to assemble party and UI icon sheets.",
    dir: "assets/images/pokemon/icons",
  },
  {
    key: "pokemon_icon_sheets",
    priority: "required",
    description: "Prebaked party and dex icon sprite sheets.",
    globPrefix: "assets/images/pokemon_icons_",
  },
  {
    key: "ui_skin",
    priority: "required",
    description: "Core UI chrome, prompts, selectors, and menu framing.",
    dir: "assets/images/ui",
  },
  {
    key: "character_portraits",
    priority: "recommended",
    description: "Character portrait and overworld identity art.",
    dir: "assets/images/character",
  },
  {
    key: "trainer_sprites",
    priority: "recommended",
    description: "Trainer battler art and trainer-adjacent identity sprites.",
    dir: "assets/images/trainer",
  },
  {
    key: "arenas",
    priority: "recommended",
    description: "Battle backgrounds and arena tiles.",
    dir: "assets/images/arenas",
  },
  {
    key: "egg_assets",
    priority: "recommended",
    description: "Egg art and incubation visuals.",
    dir: "assets/images/egg",
  },
  {
    key: "cutscene_cg",
    priority: "optional",
    description: "Cutscene and splash artwork.",
    dir: "assets/images/cg",
  },
  {
    key: "battle_vfx",
    priority: "optional",
    description: "Battle animation frame sheets and special effects.",
    dir: "assets/battle-anims",
  },
  {
    key: "audio_cry",
    priority: "optional",
    description: "Per-species cry audio files if the reskin should fully replace Pokemon audio.",
    dir: "assets/audio/cry",
  },
  {
    key: "audio_bgm",
    priority: "optional",
    description: "Music tracks if the reskin needs a full audio identity.",
    dir: "assets/audio/bgm",
  },
];

function normalizeSlash(value) {
  return value.replaceAll(path.sep, "/");
}

function titleCase(value) {
  return value
    .split(/\s+/)
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function humanizeEnumId(enumId) {
  if (SPECIAL_DISPLAY_NAMES.has(enumId)) {
    return SPECIAL_DISPLAY_NAMES.get(enumId);
  }

  return titleCase(enumId.replaceAll("_", " "));
}

function cleanCommentLabel(value) {
  return value.replaceAll("_", " ").replace(/\s+/g, " ").trim();
}

function buildSuggestion(species) {
  const curated = CURATED_SUGGESTIONS.get(species.enumId);
  if (curated) {
    return {
      confidence: "high",
      value: curated,
      source: "curated",
    };
  }

  const compactLabel = species.name.replace(/[^A-Za-z0-9]/g, "");
  const lower = compactLabel.toLowerCase();
  let mutated = lower;

  for (const [pattern, replacement] of STEM_REPLACEMENTS) {
    if (pattern.test(mutated)) {
      mutated = mutated.replace(pattern, replacement);
      break;
    }
  }

  if (mutated === lower) {
    const prefix = FALLBACK_PREFIXES[species.dex % FALLBACK_PREFIXES.length];
    const suffix = FALLBACK_SUFFIXES[(species.dex * 7) % FALLBACK_SUFFIXES.length];
    mutated = `${prefix}${compactLabel.slice(0, 10)}${suffix}`;
  } else if (!/(ccino|doro|ella|etto|issimo|maxx|oni|tron|tastic|zillo)$/i.test(mutated)) {
    const suffix = FALLBACK_SUFFIXES[(species.dex * 3) % FALLBACK_SUFFIXES.length];
    mutated = `${mutated}${suffix}`;
  }

  return {
    confidence: "medium",
    value: mutated.charAt(0).toUpperCase() + mutated.slice(1),
    source: "generated",
  };
}

async function gitRevision(targetDir) {
  try {
    const { stdout } = await execFileAsync("git", ["-C", targetDir, "rev-parse", "--short=12", "HEAD"]);
    return stdout.trim() || null;
  } catch {
    return null;
  }
}

async function walkFiles(targetDir) {
  const entries = await fs.readdir(targetDir, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    if (entry.name === ".git" || entry.name === "node_modules") {
      continue;
    }

    const fullPath = path.join(targetDir, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await walkFiles(fullPath)));
      continue;
    }

    files.push(fullPath);
  }

  return files;
}

async function countFiles(targetDir) {
  try {
    const files = await walkFiles(targetDir);
    return {
      fileCount: files.length,
      sample: files.slice(0, 20).map(filePath => normalizeSlash(path.relative(projectRoot, filePath))),
    };
  } catch {
    return {
      fileCount: 0,
      sample: [],
    };
  }
}

async function countPrefixedFiles(prefix) {
  const parentDir = path.join(projectRoot, path.dirname(prefix));
  const basenamePrefix = path.basename(prefix);
  const files = await walkFiles(parentDir);
  const matches = files
    .map(filePath => normalizeSlash(path.relative(projectRoot, filePath)))
    .filter(filePath => path.basename(filePath).startsWith(basenamePrefix));

  return {
    fileCount: matches.length,
    sample: matches.slice(0, 20),
  };
}

function parseSpeciesEnumFile(sourceText) {
  const species = [];
  const lines = sourceText.split(/\r?\n/);
  let currentValue = 0;
  let commentLabel = null;

  for (const line of lines) {
    const commentMatch = line.match(/wiki\/(.+?)_\(/);
    if (commentMatch) {
      commentLabel = cleanCommentLabel(decodeURIComponent(commentMatch[1]));
      continue;
    }

    const entryMatch = line.match(/^\s*([A-Z0-9_]+)\s*(?:=\s*(\d+))?,?\s*$/);
    if (!entryMatch || entryMatch[1] === "export" || entryMatch[1] === "SpeciesId") {
      continue;
    }

    currentValue = entryMatch[2] ? Number(entryMatch[2]) : currentValue + 1;
    const enumId = entryMatch[1];
    const name = SPECIAL_DISPLAY_NAMES.get(enumId) || commentLabel || humanizeEnumId(enumId);
    species.push({
      dex: currentValue,
      enumId,
      name,
    });
    commentLabel = null;
  }

  return species;
}

function normalizeSpeciesBucket(relativeDir) {
  if (!relativeDir || relativeDir === ".") {
    return "front";
  }

  const parts = relativeDir.split("/").filter(Boolean);
  const bucket = [];

  if (parts.includes("variant")) {
    bucket.push("variant");
  }

  if (parts.includes("exp")) {
    bucket.push("exp");
  }

  bucket.push(parts.includes("back") ? "back" : "front");

  if (parts.includes("shiny")) {
    bucket.push("shiny");
  }

  if (parts.includes("female")) {
    bucket.push("female");
  }

  return bucket.join("_");
}

async function collectSpeciesSpriteBuckets() {
  const spriteRoot = path.join(assetsRoot, "images/pokemon");
  const files = await walkFiles(spriteRoot);
  const bySpecies = new Map();

  for (const filePath of files) {
    const relativePath = normalizeSlash(path.relative(spriteRoot, filePath));
    if (relativePath.startsWith("icons/")) {
      continue;
    }
    if (!/\.(png|json)$/i.test(relativePath)) {
      continue;
    }

    const basename = path.basename(relativePath);
    const speciesMatch = basename.match(/^(\d+)(?:-[^.]+)?\.(png|json)$/i);
    if (!speciesMatch) {
      continue;
    }

    const dex = Number(speciesMatch[1]);
    const bucket = normalizeSpeciesBucket(path.dirname(relativePath));
    const relativeProjectPath = normalizeSlash(path.join("assets/images/pokemon", relativePath));
    const speciesBuckets = bySpecies.get(dex) || {};
    const bucketFiles = speciesBuckets[bucket] || [];
    bucketFiles.push(relativeProjectPath);
    bucketFiles.sort();
    speciesBuckets[bucket] = bucketFiles;
    bySpecies.set(dex, speciesBuckets);
  }

  return bySpecies;
}

async function buildAssetBuckets() {
  const buckets = [];

  for (const spec of ASSET_BUCKET_SPECS) {
    if (spec.paths) {
      const existing = [];
      for (const relativePath of spec.paths) {
        try {
          await fs.access(path.join(projectRoot, relativePath));
          existing.push(relativePath);
        } catch {
          // Skip missing path entries.
        }
      }

      buckets.push({
        description: spec.description,
        fileCount: existing.length,
        key: spec.key,
        paths: existing,
        priority: spec.priority,
      });
      continue;
    }

    const counts = spec.dir
      ? await countFiles(path.join(projectRoot, spec.dir))
      : await countPrefixedFiles(spec.globPrefix);

    buckets.push({
      description: spec.description,
      fileCount: counts.fileCount,
      key: spec.key,
      path: spec.dir || spec.globPrefix,
      priority: spec.priority,
      sample: counts.sample,
    });
  }

  return buckets;
}

function orderedSpriteBuckets(spriteBuckets) {
  const ordered = {};
  for (const bucket of SPECIES_BUCKET_ORDER) {
    if (spriteBuckets[bucket]?.length > 0) {
      ordered[bucket] = spriteBuckets[bucket];
    }
  }

  for (const [bucket, files] of Object.entries(spriteBuckets)) {
    if (!ordered[bucket]) {
      ordered[bucket] = files;
    }
  }

  return ordered;
}

async function main() {
  const [speciesSource, assetBuckets, speciesSpriteBuckets, upstreamRev, assetsRev, localesRev] = await Promise.all([
    fs.readFile(speciesEnumPath, "utf8"),
    buildAssetBuckets(),
    collectSpeciesSpriteBuckets(),
    gitRevision(projectRoot),
    gitRevision(path.join(projectRoot, "assets")),
    gitRevision(path.join(projectRoot, "locales")),
  ]);

  const species = parseSpeciesEnumFile(speciesSource).map(record => {
    const suggestion = buildSuggestion(record);
    const spriteBuckets = orderedSpriteBuckets(speciesSpriteBuckets.get(record.dex) || {});

    return {
      dex: record.dex,
      name: record.name,
      enumId: record.enumId,
      suggestedBrainrotEquivalent: suggestion.value,
      suggestionConfidence: suggestion.confidence,
      suggestionSource: suggestion.source,
      requiredDeliverables: [
        "brainrot_name",
        "front_sprite_atlas",
        "back_sprite_atlas",
        "party_icon_slot",
        "dex_copy_update",
      ],
      presentSpriteBuckets: spriteBuckets,
    };
  });

  const manifest = {
    generatedAt: new Date().toISOString(),
    project: "mogger-mon",
    upstream: {
      mogmonRevision: upstreamRev,
      assetsRevision: assetsRev,
      localesRevision: localesRev,
    },
    summary: {
      assetBucketCount: assetBuckets.length,
      speciesCount: species.length,
      curatedSuggestionCount: species.filter(item => item.suggestionSource === "curated").length,
      generatedSuggestionCount: species.filter(item => item.suggestionSource === "generated").length,
    },
    notes: [
      "This manifest is a production planning artifact for a Mogger Mon asset replacement pass.",
      "Sprite buckets reflect what the current Pokerogue-derived asset tree actually expects.",
      "Suggested brainrot equivalents are naming prompts, not final canon. Curated rows are strongest starting points.",
    ],
    assetBuckets,
    species,
  };

  await fs.writeFile(outputPath, `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(`Wrote ${outputPath}`);
}

await main();

import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const LOCALES_DIR = path.join(ROOT, "locales");
const ENGLISH_POKEMON_FILE = path.join(LOCALES_DIR, "en", "pokemon.json");
const EVOLUTIONS_SOURCE_FILE = path.join(ROOT, "src", "data", "balance", "pokemon-evolutions.ts");
const GEN1_REFERENCE_FILE = path.join(
  ROOT,
  "output",
  "private-generation-prompts",
  "brainrot-wiki",
  "gen1-reference.json",
);
const OUTPUT_DIR = path.join(ROOT, "output", "private-generation-prompts", "brainrot-wiki");
const FAMILY_MAP_FILE = path.join(OUTPUT_DIR, "gen1-family-map.json");
const FAMILY_MAP_TSV_FILE = path.join(OUTPUT_DIR, "gen1-family-map.tsv");
const PAGE_SIZE = 151;

function enumNameToSpeciesKey(enumName) {
  const parts = enumName.toLowerCase().split("_");
  return parts.map((part, index) => (index === 0 ? part : `${part[0].toUpperCase()}${part.slice(1)}`)).join("");
}

function parseEvolutionGraph(sourceText, allowedKeys) {
  const adjacency = new Map();
  let currentSource = null;

  for (const rawLine of sourceText.split("\n")) {
    const line = rawLine.trim();
    const sourceMatch = line.match(/^\[SpeciesId\.([A-Z0-9_]+)\]: \[$/);
    if (sourceMatch) {
      currentSource = enumNameToSpeciesKey(sourceMatch[1]);
      if (!adjacency.has(currentSource)) {
        adjacency.set(currentSource, []);
      }
      continue;
    }

    if (line === "]," || line === "]," || line === "],") {
      currentSource = null;
      continue;
    }

    if (!currentSource || !allowedKeys.has(currentSource)) {
      continue;
    }

    const targetMatch = line.match(/new Species(?:Form)?Evolution\(SpeciesId\.([A-Z0-9_]+)/);
    if (!targetMatch) {
      continue;
    }

    const targetKey = enumNameToSpeciesKey(targetMatch[1]);
    if (allowedKeys.has(targetKey)) {
      adjacency.get(currentSource).push(targetKey);
    }
  }

  return adjacency;
}

function collectFamily(rootKey, adjacency) {
  const queue = [{ key: rootKey, depth: 0 }];
  const visited = new Set();
  const members = [];

  while (queue.length > 0) {
    const current = queue.shift();
    if (visited.has(current.key)) {
      continue;
    }
    visited.add(current.key);
    members.push(current);

    for (const child of adjacency.get(current.key) ?? []) {
      queue.push({ key: child, depth: current.depth + 1 });
    }
  }

  return members;
}

function getStageMeta(member, maxDepth, isBranchFinal) {
  if (maxDepth === 0) {
    return {
      stageLabel: "solo",
      stagePrompt:
        "Keep the same core brainrot identity, but make it read as a complete standalone battler with a clean silhouette and no extra clutter.",
    };
  }

  if (member.depth === 0) {
    return {
      stageLabel: "base",
      stagePrompt:
        "This is the base stage of the same brainrot. Keep it smaller, cuter, simpler, and less threatening than later evolutions.",
    };
  }

  if (member.depth === maxDepth) {
    return {
      stageLabel: isBranchFinal ? "branch-final" : "final",
      stagePrompt:
        "This is the final evolution of the same brainrot. Make it bigger, tougher, and more menacing while preserving the same recognizable brainrot identity.",
    };
  }

  return {
    stageLabel: "mid",
    stagePrompt:
      "This is a middle evolution of the same brainrot. Make it more mature, tougher, and more confident than the base form, but not fully monstrous yet.",
  };
}

function toTsv(rows) {
  const header = [
    "familyRoot",
    "canonicalBrainrot",
    "familyMembers",
    "speciesKey",
    "generatedName",
    "stageLabel",
    "stagePrompt",
    "referenceImage",
  ];
  const lines = [header.join("\t")];

  for (const row of rows) {
    for (const member of row.members) {
      lines.push(
        [
          row.familyRoot,
          row.canonicalBrainrot.title,
          row.members.map(entry => entry.speciesKey).join(" > "),
          member.speciesKey,
          member.generatedName,
          member.stageLabel,
          member.stagePrompt,
          row.canonicalBrainrot.localImagePath || "",
        ]
          .map(value => value.replaceAll("\t", " "))
          .join("\t"),
      );
    }
  }

  return `${lines.join("\n")}\n`;
}

async function main() {
  const englishPokemon = JSON.parse(await fs.readFile(ENGLISH_POKEMON_FILE, "utf8"));
  const gen1Reference = JSON.parse(await fs.readFile(GEN1_REFERENCE_FILE, "utf8"));
  const evolutionsSource = await fs.readFile(EVOLUTIONS_SOURCE_FILE, "utf8");
  const firstGenKeys = Object.keys(englishPokemon).slice(0, PAGE_SIZE);
  const firstGenSet = new Set(firstGenKeys);
  const adjacency = parseEvolutionGraph(evolutionsSource, firstGenSet);
  const parents = new Map();

  for (const [sourceKey, targets] of adjacency.entries()) {
    for (const targetKey of targets) {
      parents.set(targetKey, sourceKey);
    }
  }

  const referenceMap = new Map(gen1Reference.entries.map(entry => [entry.speciesKey, entry]));
  const roots = firstGenKeys.filter(key => !parents.has(key));
  const families = [];
  const seen = new Set();

  for (const rootKey of roots) {
    if (seen.has(rootKey)) {
      continue;
    }

    const familyMembers = collectFamily(rootKey, adjacency)
      .sort((left, right) => firstGenKeys.indexOf(left.key) - firstGenKeys.indexOf(right.key))
      .map(member => ({
        ...member,
        generatedName: englishPokemon[member.key],
      }));

    for (const member of familyMembers) {
      seen.add(member.key);
    }

    const rootReference = referenceMap.get(rootKey);
    const canonicalBrainrot = rootReference?.matches?.[0] ?? null;
    if (!canonicalBrainrot) {
      continue;
    }

    const maxDepth = Math.max(...familyMembers.map(member => member.depth));
    families.push({
      familyRoot: rootKey,
      canonicalBrainrot: {
        title: canonicalBrainrot.title,
        slug: canonicalBrainrot.slug,
        imageUrl: canonicalBrainrot.imageUrl,
        localImagePath: canonicalBrainrot.localImagePath,
      },
      members: familyMembers.map(member => {
        const parentKey = parents.get(member.key) ?? null;
        const isBranchFinal = !!parentKey && (adjacency.get(parentKey)?.length ?? 0) > 1;
        const stageMeta = getStageMeta(member, maxDepth, isBranchFinal);
        return {
          dex: firstGenKeys.indexOf(member.key) + 1,
          speciesKey: member.key,
          generatedName: member.generatedName,
          depth: member.depth,
          ...stageMeta,
        };
      }),
    });
  }

  await fs.writeFile(
    FAMILY_MAP_FILE,
    `${JSON.stringify(
      {
        generatedAt: new Date().toISOString(),
        source: {
          familyReference: path.relative(ROOT, GEN1_REFERENCE_FILE).replaceAll(path.sep, "/"),
          firstGenCount: PAGE_SIZE,
        },
        families,
      },
      null,
      2,
    )}\n`,
  );
  await fs.writeFile(FAMILY_MAP_TSV_FILE, toTsv(families));

  console.log(`Wrote ${families.length} family mappings to ${FAMILY_MAP_FILE}`);
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});

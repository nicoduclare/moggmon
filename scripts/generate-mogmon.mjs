#!/usr/bin/env node
/**
 * generate-mogmon.mjs
 *
 * Generates brainrot-themed sprite sheets via Gemini, using the original
 * Pokemon sprite sheets as reference images.
 *
 * Usage:
 *   node scripts/generate-mogmon.mjs [--dex 1,4,7] [--views front,back]
 *
 * Requires GEMINI_KEY env var or pass via --key flag.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const ASSETS = path.join(ROOT, "assets", "images", "pokemon");
const OUT = path.join(ROOT, "assets", "images", "mogmon");
const PROMPTS_FILE =
  process.env.MOGGER_MON_PROMPTS_FILE
  || path.join(ROOT, "output", "private-generation-prompts", "mogger-mon-prompts.json");

const API_KEY = process.env.GEMINI_KEY;

if (!API_KEY) {
  throw new Error("GEMINI_KEY is required to generate Mogger Mon sprites.");
}

// Gemini model with native image generation
const MODEL = "gemini-2.5-flash-image";
const API_URL = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent?key=${API_KEY}`;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function readImageAsBase64(filePath) {
  const buf = fs.readFileSync(filePath);
  return buf.toString("base64");
}

function getSpritePaths(dex) {
  // Returns paths for the views we want to generate
  return {
    front: path.join(ASSETS, `${dex}.png`),
    back: path.join(ASSETS, "back", `${dex}.png`),
  };
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

// ---------------------------------------------------------------------------
// Gemini API call with image input + image output
// ---------------------------------------------------------------------------

async function generateWithGemini(prompt, referenceImages) {
  // Build parts array: text prompt + all reference images
  const parts = [];

  // Add each reference image with a label
  for (const { label, base64, mimeType } of referenceImages) {
    parts.push({ text: `[Reference: ${label}]` });
    parts.push({
      inlineData: {
        mimeType: mimeType || "image/png",
        data: base64,
      },
    });
  }

  // Add the generation prompt last
  parts.push({ text: prompt });

  const body = {
    contents: [{ role: "user", parts }],
    generationConfig: {
      responseModalities: ["TEXT", "IMAGE"],
      temperature: 1.0,
    },
  };

  const res = await fetch(API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Gemini API ${res.status}: ${errText}`);
  }

  const data = await res.json();

  // Extract generated image(s) from response
  const images = [];
  const textParts = [];
  const candidates = data.candidates || [];
  for (const candidate of candidates) {
    for (const part of candidate.content?.parts || []) {
      if (part.inlineData) {
        images.push({
          base64: part.inlineData.data,
          mimeType: part.inlineData.mimeType || "image/png",
        });
      }
      if (part.text) {
        textParts.push(part.text);
      }
    }
  }

  return { images, text: textParts.join("\n") };
}

// ---------------------------------------------------------------------------
// Generate a single view (front or back) for one species
// ---------------------------------------------------------------------------

async function generateView(species, view) {
  const spritePaths = getSpritePaths(species.dex);
  const srcPath = spritePaths[view];

  if (!fs.existsSync(srcPath)) {
    console.log(`  ⏭  ${view} sprite not found at ${srcPath}, skipping`);
    return null;
  }

  // Read the original sprite sheet JSON to extract exact grid info
  const jsonPath = srcPath.replace(".png", ".json");
  let uniqueFrames = 25;
  let frameW = 37;
  let frameH = 38;
  if (fs.existsSync(jsonPath)) {
    try {
      const atlasData = JSON.parse(fs.readFileSync(jsonPath, "utf-8"));
      const tex = atlasData.textures?.[0];
      if (tex) {
        frameW = tex.frames?.[0]?.sourceSize?.w || 37;
        frameH = tex.frames?.[0]?.sourceSize?.h || 38;
        // Count unique visual positions (many logical frames share the same cell)
        const positions = new Set();
        for (const fr of tex.frames || []) {
          const f = fr.frame;
          positions.add(`${f.x},${f.y}`);
        }
        uniqueFrames = positions.size;
      }
    } catch {}
  }
  // Calculate a clean grid that fits the unique frames
  const cols = Math.ceil(Math.sqrt(uniqueFrames));
  const rows = Math.ceil(uniqueFrames / cols);
  const gridInfo = `EXACTLY ${cols} columns x ${rows} rows = ${cols * rows} cells (${uniqueFrames} filled, rest empty). Each cell is ${frameW}x${frameH} pixels. Total sheet is ${cols * frameW}x${rows * frameH} pixels.`;

  const referenceImages = [];

  // For back view: pass the already-generated front so creature design is consistent
  if (view === "back") {
    const frontOutPath = path.join(OUT, `${species.dex}.png`);
    if (fs.existsSync(frontOutPath)) {
      referenceImages.push({
        label: `This is the FRONT view of ${species.mogmon} that was already created. Draw the BACK (rear) of THIS EXACT same creature — same design, colors, and features, just viewed from behind.`,
        base64: readImageAsBase64(frontOutPath),
        mimeType: "image/png",
      });
    }
  }

  const viewDir =
    view === "front"
      ? "front-facing (creature looks TOWARD the viewer)"
      : "back-facing (creature looks AWAY from the viewer, you see its back/rear)";

  // Describe the pose in text instead of showing the original sprite
  const poseDesc =
    view === "front"
      ? "The creature stands facing the viewer in a battle-ready idle pose, slightly bouncing. Small body centered in each frame."
      : "The creature faces AWAY from the viewer (we see its back/tail/rear). Battle-ready idle pose, slightly bouncing. Small body centered in each frame.";

  const fullPrompt = `You are a pixel artist designing a BRAND NEW creature for a brainrot/meme monster battler game. You are creating it from scratch — do NOT base it on any existing character.

CREATURE NAME: "${species.mogmon}"
WHAT IT IS: A fusion of ${species.formula}. Imagine what a creature would look like if you literally combined those things into one being.

DETAILED DESIGN:
${species.prompt}

VIEW: ${viewDir}

POSE: ${poseDesc}

OUTPUT FORMAT — THIS IS STRICT, DO NOT DEVIATE:
- Pixel art animated sprite sheet
- Grid: ${gridInfo}
- DO NOT add more frames or rows than specified. The grid size is exact.
- Pixel art style (chunky pixels, limited palette, retro game aesthetic)
- Transparent background (PNG with alpha channel)
- Each frame is a slight variation of an idle animation (gentle bounce/sway)
- The creature should be small and centered within each frame cell
- NO outlines or borders around cells — just sprites arranged in a grid with transparent gaps

The creature should look like it belongs in a 2D monster-battling RPG. Think original, creative, funny, memey. It should NOT resemble any existing franchise character. Design purely from the formula: ${species.formula}.

REMEMBER: ${cols} columns, ${rows} rows. No more, no less. Generate the sprite sheet image now.`;

  console.log(`  🎨 Generating ${view} view...`);

  try {
    const result = await generateWithGemini(fullPrompt, referenceImages);

    if (result.images.length === 0) {
      console.log(`  ⚠️  No image returned for ${view}. Gemini said: ${result.text.slice(0, 200)}`);
      return null;
    }

    // Save the first generated image
    const outDir = view === "front" ? OUT : path.join(OUT, "back");
    ensureDir(outDir);
    const outPath = path.join(outDir, `${species.dex}.png`);

    const imgBuf = Buffer.from(result.images[0].base64, "base64");
    fs.writeFileSync(outPath, imgBuf);
    console.log(`  ✅ Saved ${outPath} (${(imgBuf.length / 1024).toFixed(1)}KB)`);

    if (result.text) {
      console.log(`  💬 ${result.text.slice(0, 120)}`);
    }

    return outPath;
  } catch (err) {
    console.error(`  ❌ Error generating ${view}: ${err.message}`);
    return null;
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const args = process.argv.slice(2);

  // Parse --dex flag
  let dexFilter = null;
  const dexIdx = args.indexOf("--dex");
  if (dexIdx !== -1 && args[dexIdx + 1]) {
    dexFilter = args[dexIdx + 1].split(",").map(Number);
  }

  // Parse --views flag
  let views = ["front", "back"];
  const viewIdx = args.indexOf("--views");
  if (viewIdx !== -1 && args[viewIdx + 1]) {
    views = args[viewIdx + 1].split(",");
  }

  // Load prompts
  const prompts = JSON.parse(fs.readFileSync(PROMPTS_FILE, "utf-8"));
  let species = prompts.species;

  if (dexFilter) {
    species = species.filter(s => dexFilter.includes(s.dex));
  }

  console.log("\n🧠 Mogger Mon Sprite Generator");
  console.log(`   Model: ${MODEL}`);
  console.log(`   Species: ${species.length}`);
  console.log(`   Views: ${views.join(", ")}`);
  console.log(`   Output: ${OUT}\n`);

  let generated = 0;
  let failed = 0;

  for (const sp of species) {
    console.log(`\n[${sp.dex}] ${sp.original} → ${sp.mogmon} (${sp.formula})`);

    for (const view of views) {
      const result = await generateView(sp, view);
      if (result) {
        generated++;
      } else {
        failed++;
      }

      // Small delay to avoid rate limits
      if (species.length > 1 || views.length > 1) {
        await new Promise(r => setTimeout(r, 2000));
      }
    }
  }

  console.log(`\n🏁 Done! Generated: ${generated}, Failed: ${failed}`);
  console.log(`   Output directory: ${OUT}`);
}

main().catch(err => {
  console.error("Fatal:", err);
  process.exit(1);
});

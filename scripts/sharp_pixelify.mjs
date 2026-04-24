#!/usr/bin/env node

import { existsSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

function loadSharp() {
  const localRequire = createRequire(import.meta.url);
  try {
    return localRequire("sharp");
  } catch {
    const tempaiTownBackendPackage = resolve(__dirname, "../../../aura/tempaitown/backend/package.json");
    if (!existsSync(tempaiTownBackendPackage)) {
      throw new Error(
        `sharp is not installed locally and TempaiTown backend package was not found: ${tempaiTownBackendPackage}`,
      );
    }
    return createRequire(tempaiTownBackendPackage)("sharp");
  }
}

function parsePositiveInteger(value, fallback) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function parseArgs(argv) {
  const options = {
    baseWidth: 32,
    outputWidth: 0,
    outputHeight: 0,
    files: [],
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--base-width" && argv[index + 1]) {
      options.baseWidth = parsePositiveInteger(argv[index + 1], options.baseWidth);
      index += 1;
    } else if (arg === "--width" && argv[index + 1]) {
      options.outputWidth = parsePositiveInteger(argv[index + 1], options.outputWidth);
      index += 1;
    } else if (arg === "--height" && argv[index + 1]) {
      options.outputHeight = parsePositiveInteger(argv[index + 1], options.outputHeight);
      index += 1;
    } else {
      options.files.push(arg);
    }
  }

  if (options.files.length < 2) {
    throw new Error(
      "Usage: node scripts/sharp_pixelify.mjs [--base-width 32] [--width W] [--height H] <input> <output>",
    );
  }

  return {
    ...options,
    input: resolve(options.files[0]),
    output: resolve(options.files[1]),
  };
}

async function main() {
  const sharp = loadSharp();
  const options = parseArgs(process.argv.slice(2));
  const metadata = await sharp(options.input).metadata();
  if (!metadata.width || !metadata.height) {
    throw new Error(`Unable to determine image dimensions: ${options.input}`);
  }

  const outputWidth = options.outputWidth || metadata.width;
  const outputHeight =
    options.outputHeight || Math.max(1, Math.round((metadata.height * outputWidth) / metadata.width));
  const baseWidth = Math.max(1, Math.min(options.baseWidth, metadata.width, outputWidth));
  const baseHeight = Math.max(1, Math.round((metadata.height * baseWidth) / metadata.width));

  const reduced = await sharp(options.input)
    .ensureAlpha()
    .resize(baseWidth, baseHeight, {
      kernel: sharp.kernel.nearest,
      fit: "fill",
    })
    .png({ compressionLevel: 9 })
    .toBuffer();

  await sharp(reduced)
    .resize(outputWidth, outputHeight, {
      kernel: sharp.kernel.nearest,
      fit: "fill",
    })
    .png({ compressionLevel: 9 })
    .toFile(options.output);

  process.stdout.write(
    `${JSON.stringify({
      runtime: "sharp",
      input: { width: metadata.width, height: metadata.height },
      base: { width: baseWidth, height: baseHeight },
      output: { width: outputWidth, height: outputHeight, path: options.output },
    })}\n`,
  );
}

main().catch(error => {
  process.stderr.write(`${error instanceof Error ? error.stack || error.message : String(error)}\n`);
  process.exit(1);
});

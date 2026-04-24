#!/usr/bin/env node

import { existsSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DEFAULT_MODEL = process.env.MOGMON_GEMINI_MPP_MODEL || "gemini-3.1-flash-image-preview";
const DEFAULT_MAX_SPEND = process.env.MOGMON_GEMINI_MPP_MAX_SPEND || "0.01";
const GEMINI_MPP_SERVICE_URL = "https://gemini.mpp.tempo.xyz";

function resolveAuraRoot() {
  const candidates = [
    process.env.MOGMON_AURA_ROOT,
    path.resolve(__dirname, "../../../aura"),
    "/Users/alyssa/src/aura",
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  throw new Error("Could not find Aura repo. Set MOGMON_AURA_ROOT to the local /Users/alyssa/src/aura checkout.");
}

async function loadAuraModules(auraRoot) {
  const backendPackageJson = path.join(auraRoot, "tempaitown/backend/package.json");
  if (!existsSync(backendPackageJson)) {
    throw new Error(`Aura backend package.json not found: ${backendPackageJson}`);
  }

  const backendRequire = createRequire(backendPackageJson);
  const { Mppx, tempo } = await import(pathToFileURL(backendRequire.resolve("mppx/client")).href);
  const { resolveMppPayerAccount } = await import(pathToFileURL(path.join(auraRoot, "experiments/mpp-payer.mjs")).href);

  return { Mppx, tempo, resolveMppPayerAccount };
}

async function readStdinJson() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  const raw = Buffer.concat(chunks).toString("utf8").trim();
  if (!raw) {
    return {};
  }
  return JSON.parse(raw);
}

function buildParts(prompt, referenceImages = []) {
  const parts = [];
  for (const ref of referenceImages) {
    parts.push({ text: `[Reference: ${ref.label}]` });
    parts.push({
      inlineData: {
        mimeType: ref.mime_type,
        data: ref.base64,
      },
    });
  }
  parts.push({ text: prompt });
  return parts;
}

function collectResponseParts(data) {
  const images = [];
  const texts = [];

  for (const candidate of data?.candidates || []) {
    for (const part of candidate?.content?.parts || []) {
      if (part?.inlineData?.data) {
        images.push({
          base64: part.inlineData.data,
          mime_type: part.inlineData.mimeType || "image/png",
        });
      }
      if (typeof part?.text === "string" && part.text.trim()) {
        texts.push(part.text);
      }
    }
  }

  return {
    images,
    text: texts.join("\n"),
  };
}

async function generateViaMpp(input) {
  const auraRoot = resolveAuraRoot();
  const { Mppx, tempo, resolveMppPayerAccount } = await loadAuraModules(auraRoot);
  const account = resolveMppPayerAccount();

  if (input.resolveOnly) {
    return {
      auraRoot,
      maxSpend: trimString(input.maxSpend) || DEFAULT_MAX_SPEND,
      model: `mpp:${trimString(input.model) || DEFAULT_MODEL}`,
      payerAddress: account?.address || null,
      resolveOnly: true,
    };
  }

  const requestBody = {
    contents: [
      {
        role: "user",
        parts: buildParts(input.prompt, input.referenceImages || []),
      },
    ],
    generationConfig: {
      responseModalities: ["TEXT", "IMAGE"],
      temperature: Number.isFinite(Number(input.temperature)) ? Number(input.temperature) : 1.0,
      imageConfig: {
        imageSize: "1K",
      },
    },
  };

  const model = trimString(input.model) || DEFAULT_MODEL;
  const mppx = Mppx.create({
    methods: [
      tempo({
        account,
        autoSwap: true,
        maxDeposit: trimString(input.maxSpend) || DEFAULT_MAX_SPEND,
      }),
    ],
    polyfill: false,
  });

  const response = await mppx.fetch(
    `${GEMINI_MPP_SERVICE_URL}/v1beta/models/${encodeURIComponent(model)}:generateContent`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(requestBody),
    },
  );

  const rawText = await response.text();
  let data = null;
  try {
    data = JSON.parse(rawText);
  } catch {
    data = null;
  }

  if (!response.ok) {
    const details = data ? JSON.stringify(data) : rawText;
    throw new Error(`Gemini MPP ${response.status}: ${details.slice(0, 1200)}`);
  }
  if (!data) {
    throw new Error("Gemini MPP returned a non-JSON response body.");
  }

  return {
    auraRoot,
    maxSpend: trimString(input.maxSpend) || DEFAULT_MAX_SPEND,
    model: `mpp:${model}`,
    payerAddress: account?.address || null,
    ...collectResponseParts(data),
  };
}

function trimString(value) {
  return String(value || "").trim();
}

async function main() {
  const resolveOnly = process.argv.includes("--resolve-only");
  const input = await readStdinJson();
  const result = await generateViaMpp({
    ...input,
    resolveOnly,
  });
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

main().catch(error => {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
});

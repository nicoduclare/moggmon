#!/usr/bin/env node

import { existsSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DEFAULT_MODEL = process.env.MOGMON_FAL_MPP_MODEL || "xai/grok-imagine-image/edit";
const DEFAULT_MAX_SPEND = process.env.MOGMON_FAL_MPP_MAX_SPEND || "0.03";
const FAL_MPP_SERVICE_URL = "https://fal.mpp.tempo.xyz";

function resolveAuraRoot() {
  const candidates = [
    process.env.MOGMON_AURA_ROOT,
    path.resolve(__dirname, "../../../aura"),
    "../aura",
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  throw new Error("Could not find Aura repo. Set MOGMON_AURA_ROOT to the local ../aura checkout.");
}

async function loadAuraModules(auraRoot) {
  const backendPackageJson = path.join(auraRoot, "tempaitown/backend/package.json");
  if (!existsSync(backendPackageJson)) {
    throw new Error(`Aura backend package.json not found: ${backendPackageJson}`);
  }

  const backendRequire = createRequire(backendPackageJson);
  const { Mppx, tempo } = await import(pathToFileURL(backendRequire.resolve("mppx/client")).href);
  const { Account: TempoAccount } = await import(pathToFileURL(backendRequire.resolve("viem/tempo")).href);
  const { resolveMppPayerAccount } = await import(pathToFileURL(path.join(auraRoot, "experiments/mpp-payer.mjs")).href);

  return { Mppx, TempoAccount, tempo, resolveMppPayerAccount };
}

async function readStdinJson() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  const raw = Buffer.concat(chunks).toString("utf8").trim();
  return raw ? JSON.parse(raw) : {};
}

function trimString(value) {
  return String(value || "").trim();
}

function readTempoE2eBundle() {
  const rawBundle = trimString(process.env.TEMPO_E2E_AGENT_BUNDLE_JSON || process.env.TEMPO_AGENT_BUNDLE_JSON);
  if (!rawBundle) {
    return null;
  }

  try {
    return JSON.parse(rawBundle);
  } catch {
    return null;
  }
}

function resolveTempoE2eBundleAccount(TempoAccount) {
  if (trimString(process.env.MOGMON_FAL_MPP_USE_BACKEND_PAYER).toLowerCase() === "1") {
    return null;
  }

  const bundle = readTempoE2eBundle();
  if (!bundle) {
    return null;
  }

  const accessPrivateKey = trimString(bundle.privateKey || bundle.accessKeyPrivateKey);
  const rootAddress = trimString(bundle.wallet || bundle.walletAddress);
  if (accessPrivateKey && rootAddress) {
    return TempoAccount.fromSecp256k1(accessPrivateKey, { access: rootAddress });
  }
  if (accessPrivateKey) {
    return TempoAccount.fromSecp256k1(accessPrivateKey);
  }
  return null;
}

function asDataUrl(image) {
  const mimeType = image.mime_type || image.mimeType || "image/png";
  return `data:${mimeType};base64,${image.base64}`;
}

function buildFalBody(input) {
  if (input.body && typeof input.body === "object" && !Array.isArray(input.body)) {
    return input.body;
  }

  const referenceImages = Array.isArray(input.referenceImages) ? input.referenceImages : [];
  return {
    prompt: input.prompt,
    ...(referenceImages.length > 0 ? { image_urls: referenceImages.map(asDataUrl) } : {}),
    num_images: Number.isFinite(Number(input.numImages)) ? Number(input.numImages) : 1,
    output_format: trimString(input.outputFormat) || "png",
    ...(input.resolution ? { resolution: input.resolution } : {}),
    ...(input.imageSize ? { image_size: input.imageSize } : {}),
    ...(input.background ? { background: input.background } : {}),
    ...(input.quality ? { quality: input.quality } : {}),
    ...(input.inputFidelity ? { input_fidelity: input.inputFidelity } : {}),
  };
}

function asArray(value) {
  if (!value) {
    return [];
  }
  return Array.isArray(value) ? value : [value];
}

function encodeMppModelPath(model) {
  if (model.includes("%2F") || model.includes("%2f")) {
    return model;
  }
  const parts = model.split("/");
  if (parts.length <= 3) {
    return model;
  }
  return [...parts.slice(0, 2), encodeURIComponent(parts.slice(2).join("/"))].join("/");
}

async function generateViaMpp(input) {
  const auraRoot = resolveAuraRoot();
  const { Mppx, TempoAccount, tempo, resolveMppPayerAccount } = await loadAuraModules(auraRoot);
  const account = resolveTempoE2eBundleAccount(TempoAccount) || resolveMppPayerAccount();
  const model = trimString(input.model) || DEFAULT_MODEL;
  const maxSpend = trimString(input.maxSpend) || DEFAULT_MAX_SPEND;

  if (input.resolveOnly) {
    return {
      auraRoot,
      maxSpend,
      model: `mpp:${model}`,
      payerAddress: account?.address || null,
      resolveOnly: true,
    };
  }

  const mppx = Mppx.create({
    methods: [
      tempo({
        account,
        autoSwap: true,
        maxDeposit: maxSpend,
      }),
    ],
    polyfill: false,
  });

  const response = await mppx.fetch(`${FAL_MPP_SERVICE_URL}/${encodeMppModelPath(model)}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(buildFalBody(input)),
  });

  const rawText = await response.text();
  let data = null;
  try {
    data = JSON.parse(rawText);
  } catch {
    data = null;
  }

  if (!response.ok) {
    const details = data ? JSON.stringify(data) : rawText;
    throw new Error(`Fal MPP ${response.status}: ${details.slice(0, 1200)}`);
  }
  if (!data) {
    throw new Error("Fal MPP returned a non-JSON response body.");
  }

  return {
    auraRoot,
    maxSpend,
    model: `mpp:${model}`,
    payerAddress: account?.address || null,
    images: data.images || (data.image ? [data.image] : []),
    audio: asArray(data.audio || data.audios),
    files: asArray(data.file || data.files),
    raw: data,
  };
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

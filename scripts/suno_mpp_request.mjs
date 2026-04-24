#!/usr/bin/env node

import { existsSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DEFAULT_MAX_SPEND = process.env.MOGMON_SUNO_MPP_MAX_SPEND || "0.12";
const SUNO_MPP_SERVICE_URL = "https://suno.mpp.paywithlocus.com/suno";

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}

function trimString(value) {
  return String(value || "").trim();
}

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
  return raw ? JSON.parse(raw) : {};
}

function normalizeEndpoint(endpoint) {
  const value = trimString(endpoint || "/generate-music");
  return value.startsWith("/") ? value : `/${value}`;
}

async function requestViaMpp(input) {
  const auraRoot = resolveAuraRoot();
  const { Mppx, tempo, resolveMppPayerAccount } = await loadAuraModules(auraRoot);
  const account = resolveMppPayerAccount();
  const endpoint = normalizeEndpoint(input.endpoint);
  const maxSpend = trimString(input.maxSpend) || DEFAULT_MAX_SPEND;

  if (input.resolveOnly) {
    return {
      auraRoot,
      endpoint,
      maxSpend,
      payerAddress: account?.address || null,
      provider: "suno-mpp",
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

  const response = await mppx.fetch(`${SUNO_MPP_SERVICE_URL}${endpoint}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(input.body || {}),
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
    throw new Error(`Suno MPP ${response.status}: ${details.slice(0, 1200)}`);
  }
  if (!data) {
    throw new Error("Suno MPP returned a non-JSON response body.");
  }

  return {
    auraRoot,
    endpoint,
    maxSpend,
    payerAddress: account?.address || null,
    provider: "suno-mpp",
    raw: data,
  };
}

async function main() {
  const resolveOnly = process.argv.includes("--resolve-only");
  const input = await readStdinJson();
  const result = await requestViaMpp({
    ...input,
    resolveOnly,
  });
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

main().catch(error => {
  const message = error instanceof Error ? error.message : String(error);
  fail(message);
});

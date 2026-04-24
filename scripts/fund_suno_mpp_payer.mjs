#!/usr/bin/env node

import { existsSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const AURA_BACKEND_ROOT = process.env.MOGMON_AURA_BACKEND_ROOT || "/Users/alyssa/src/aura/tempaitown/backend";
const backendRequire = createRequire(path.join(AURA_BACKEND_ROOT, "package.json"));

const { erc20Abi, formatUnits, parseUnits } = backendRequire("viem");
const { writeContractSync } = backendRequire("viem/actions");
const { Actions, Addresses } = await import(pathToFileURL(backendRequire.resolve("viem/tempo")).href);
const { TEMPO_USDC_ADDRESS } = backendRequire(path.join(AURA_BACKEND_ROOT, "lib/tempoBridge.js"));
const {
  createTempoDelegatedAgentWalletClient,
  createTempoFeePayerClient,
  createTempoPublicClient,
  resolveTempoPathUsd,
} = backendRequire(path.join(AURA_BACKEND_ROOT, "lib/tempoRuntime.js"));

function argValue(name, fallback = "") {
  const index = process.argv.indexOf(name);
  if (index === -1 || index + 1 >= process.argv.length) {
    return fallback;
  }
  return process.argv[index + 1];
}

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}

function stripWrappingQuotes(value) {
  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
    return value.slice(1, -1);
  }
  return value;
}

function parseDotEnvFile(filePath) {
  if (!existsSync(filePath)) {
    return {};
  }
  const entries = {};
  for (const line of readFileSync(filePath, "utf8").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }
    const match = trimmed.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    if (!match) {
      continue;
    }
    entries[match[1]] = stripWrappingQuotes(match[2].trim());
  }
  return entries;
}

function loadBundle() {
  const raw = process.env.TEMPO_E2E_AGENT_BUNDLE_JSON || process.env.TEMPO_AGENT_BUNDLE_JSON;
  if (!raw) {
    fail("TEMPO_E2E_AGENT_BUNDLE_JSON or TEMPO_AGENT_BUNDLE_JSON is required");
  }
  try {
    return JSON.parse(raw);
  } catch {
    fail("Tempo bundle env var is not valid JSON");
  }
}

async function readTokenBalance(client, token, owner) {
  const [raw, decimals, symbol] = await Promise.all([
    client.readContract({ address: token, abi: erc20Abi, functionName: "balanceOf", args: [owner] }),
    client.readContract({ address: token, abi: erc20Abi, functionName: "decimals" }),
    client.readContract({ address: token, abi: erc20Abi, functionName: "symbol" }),
  ]);
  return { raw: raw.toString(), formatted: formatUnits(raw, decimals), symbol };
}

async function main() {
  const localAddress = argValue("--local-address", "0x10fa11cb5D099a92d28A08F8966D9bF04C4D6280");
  const transferPathUsd = argValue("--transfer-pathusd", "25.5");
  const buyUsdc = argValue("--buy-usdc", "24.5");
  const slippageBps = BigInt(argValue("--slippage-bps", "200"));
  const bundle = loadBundle();
  const env = {
    ...parseDotEnvFile(path.join(AURA_BACKEND_ROOT, ".env")),
    ...process.env,
  };

  const publicClient = createTempoPublicClient({ env });
  const pathUsd = resolveTempoPathUsd(env);
  const transferAmount = parseUnits(transferPathUsd, 6);
  const buyAmountOut = parseUnits(buyUsdc, 6);
  const quoteAmountIn = await Actions.dex.getBuyQuote(publicClient, {
    amountOut: buyAmountOut,
    tokenIn: pathUsd,
    tokenOut: TEMPO_USDC_ADDRESS,
  });
  const maxAmountIn = (quoteAmountIn * (10_000n + slippageBps) + 9_999n) / 10_000n;

  const delegated = createTempoDelegatedAgentWalletClient({
    accessKeyPrivateKey: bundle.privateKey || bundle.accessKeyPrivateKey,
    accessRootAddress: bundle.wallet || bundle.walletAddress,
    env,
  });
  const feePayer = createTempoFeePayerClient({ env });
  if (!feePayer) {
    fail("No local TEMPO_FEE_PAYER_PRIVATE_KEY is configured");
  }
  const allowance = await publicClient.readContract({
    address: pathUsd,
    abi: erc20Abi,
    functionName: "allowance",
    args: [localAddress, Addresses.stablecoinDex],
  });
  const transactions = [];
  if (transferAmount > 0n) {
    const transferReceipt = await writeContractSync(delegated.client, {
      address: pathUsd,
      abi: erc20Abi,
      functionName: "transfer",
      args: [localAddress, transferAmount],
      account: delegated.account,
    });
    transactions.push({ kind: "transfer_pathusd_to_local", txHash: transferReceipt.transactionHash });
  }
  if (allowance < maxAmountIn) {
    const approveReceipt = await writeContractSync(feePayer.client, {
      address: pathUsd,
      abi: erc20Abi,
      functionName: "approve",
      args: [Addresses.stablecoinDex, maxAmountIn],
      account: feePayer.account,
    });
    transactions.push({ kind: "approve_local_pathusd", txHash: approveReceipt.transactionHash });
  }

  const buyResult = await Actions.dex.buySync(feePayer.client, {
    amountOut: buyAmountOut,
    maxAmountIn,
    tokenIn: pathUsd,
    tokenOut: TEMPO_USDC_ADDRESS,
    account: feePayer.account,
  });
  transactions.push({ kind: "buy_local_usdc", txHash: buyResult.receipt.transactionHash });

  const balances = {
    localPathUsd: await readTokenBalance(publicClient, pathUsd, localAddress),
    localTempoUsdc: await readTokenBalance(publicClient, TEMPO_USDC_ADDRESS, localAddress),
  };
  process.stdout.write(
    `${JSON.stringify(
      {
        transactions,
        quote: {
          buyUsdc,
          maxAmountInPathUsd: formatUnits(maxAmountIn, 6),
          quotedAmountInPathUsd: formatUnits(quoteAmountIn, 6),
          transferPathUsd,
        },
        balances,
      },
      null,
      2,
    )}\n`,
  );
}

main().catch(error => fail(error instanceof Error ? error.message : String(error)));

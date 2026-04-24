#!/usr/bin/env node

import { fal } from "@fal-ai/client";

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
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

function inferMimeType(image) {
  return image.mime_type || image.mimeType || "image/png";
}

function inferFileName(image, index) {
  return image.file_name || image.fileName || `reference-${index + 1}.png`;
}

async function uploadReferenceImages(referenceImages) {
  const urls = [];
  for (const [index, image] of referenceImages.entries()) {
    const bytes = Buffer.from(image.base64, "base64");
    const file = new File([bytes], inferFileName(image, index), { type: inferMimeType(image) });
    urls.push(await fal.storage.upload(file));
  }
  return urls;
}

async function uploadDataUrl(dataUrl, fileName = "input.png") {
  const match = /^data:([^;,]+)?(?:;base64)?,(.*)$/s.exec(dataUrl);
  if (!match) {
    return dataUrl;
  }
  const mimeType = match[1] || "image/png";
  const payload = match[2] || "";
  const bytes = dataUrl.includes(";base64,")
    ? Buffer.from(payload, "base64")
    : Buffer.from(decodeURIComponent(payload), "utf8");
  const file = new File([bytes], fileName, { type: mimeType });
  return fal.storage.upload(file);
}

function asArray(value) {
  if (!value) {
    return [];
  }
  return Array.isArray(value) ? value : [value];
}

async function buildFalBody(input) {
  if (input.body && typeof input.body === "object" && !Array.isArray(input.body)) {
    const body = { ...input.body };
    if (typeof body.image_url === "string" && body.image_url.startsWith("data:")) {
      body.image_url = await uploadDataUrl(body.image_url, "image.png");
    }
    if (typeof body.mask_url === "string" && body.mask_url.startsWith("data:")) {
      body.mask_url = await uploadDataUrl(body.mask_url, "mask.png");
    }
    if (typeof body.mask_image_url === "string" && body.mask_image_url.startsWith("data:")) {
      body.mask_image_url = await uploadDataUrl(body.mask_image_url, "mask.png");
    }
    return body;
  }

  const referenceImages = Array.isArray(input.referenceImages) ? input.referenceImages : [];
  const imageUrls = await uploadReferenceImages(referenceImages);
  return {
    prompt: input.prompt,
    ...(imageUrls.length > 0 ? { image_urls: imageUrls } : {}),
    num_images: Number.isFinite(Number(input.numImages)) ? Number(input.numImages) : 1,
    output_format: trimString(input.outputFormat) || "png",
    ...(input.resolution ? { resolution: input.resolution } : {}),
    ...(input.imageSize ? { image_size: input.imageSize } : {}),
    ...(input.background ? { background: input.background } : {}),
    ...(input.quality ? { quality: input.quality } : {}),
    ...(input.inputFidelity ? { input_fidelity: input.inputFidelity } : {}),
  };
}

async function main() {
  const credentials = process.env.FAL_KEY || process.env.FAL_API_KEY;
  if (!credentials) {
    fail("FAL 401: missing FAL_KEY or FAL_API_KEY in the environment");
  }
  fal.config({ credentials });

  const input = await readStdinJson();
  const model = trimString(input.model) || "xai/grok-imagine-image/edit";
  const result = await fal.subscribe(model, {
    input: await buildFalBody(input),
    logs: true,
    onQueueUpdate: update => {
      if (update.status === "IN_PROGRESS" && Array.isArray(update.logs)) {
        for (const log of update.logs) {
          process.stderr.write(`[fal] ${log.message}\n`);
        }
      }
    },
  });
  const data = result.data || {};
  process.stdout.write(
    `${JSON.stringify({
      model: `fal:${model}`,
      requestId: result.requestId,
      images: data.images || (data.image ? [data.image] : []),
      audio: asArray(data.audio || data.audios),
      files: asArray(data.file || data.files),
      raw: data,
    })}\n`,
  );
}

main().catch(error => {
  const message = error instanceof Error ? error.message : String(error);
  fail(`FAL request failed: ${message}`);
});

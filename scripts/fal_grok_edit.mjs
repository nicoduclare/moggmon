#!/usr/bin/env node

import { fal } from "@fal-ai/client";

const MODEL = "xai/grok-imagine-image/edit";

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
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
    const mimeType = inferMimeType(image);
    const fileName = inferFileName(image, index);
    const bytes = Buffer.from(image.base64, "base64");
    const file = new File([bytes], fileName, { type: mimeType });
    const url = await fal.storage.upload(file);
    urls.push(url);
  }
  return urls;
}

async function main() {
  const raw = await new Promise((resolve, reject) => {
    const chunks = [];
    process.stdin.on("data", chunk => chunks.push(chunk));
    process.stdin.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    process.stdin.on("error", reject);
  });

  const payload = JSON.parse(raw || "{}");
  const credentials = process.env.FAL_KEY || process.env.FAL_API_KEY;
  if (!credentials) {
    fail("FAL 401: missing FAL_KEY or FAL_API_KEY in the environment");
  }

  fal.config({ credentials });

  const imageUrls = await uploadReferenceImages(payload.referenceImages || []);
  if (imageUrls.length === 0) {
    fail(`FAL 400: ${payload.model || MODEL} requires at least one reference image`);
  }
  const maskUrls = payload.maskImage ? await uploadReferenceImages([payload.maskImage]) : [];

  try {
    const input = {
      prompt: payload.prompt,
      image_urls: imageUrls,
      num_images: payload.numImages || 1,
      output_format: payload.outputFormat || "jpeg",
    };
    if (payload.resolution) {
      input.resolution = payload.resolution;
    }
    if (payload.imageSize) {
      input.image_size = payload.imageSize;
    }
    if (payload.background) {
      input.background = payload.background;
    }
    if (payload.quality) {
      input.quality = payload.quality;
    }
    if (payload.inputFidelity) {
      input.input_fidelity = payload.inputFidelity;
    }
    if (maskUrls[0]) {
      input.mask_image_url = maskUrls[0];
    }

    const result = await fal.subscribe(payload.model || MODEL, {
      input,
      logs: true,
      onQueueUpdate: update => {
        if (update.status === "IN_PROGRESS" && Array.isArray(update.logs)) {
          for (const log of update.logs) {
            process.stderr.write(`[fal] ${log.message}\n`);
          }
        }
      },
    });

    process.stdout.write(
      `${JSON.stringify(
        {
          model: `fal:${payload.model || MODEL}`,
          requestId: result.requestId,
          revised_prompt: result.data?.revised_prompt || "",
          images: result.data?.images || [],
        },
        null,
        2,
      )}\n`,
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const details = {};
    for (const key of Object.getOwnPropertyNames(error)) {
      if (key === "stack" || key === "message" || key === "name") {
        continue;
      }
      details[key] = error[key];
    }
    const detailText = Object.keys(details).length > 0 ? ` ${JSON.stringify(details).slice(0, 2000)}` : "";
    fail(`FAL request failed: ${message}${detailText}`);
  }
}

main().catch(error => {
  const message = error instanceof Error ? error.stack || error.message : String(error);
  fail(message);
});

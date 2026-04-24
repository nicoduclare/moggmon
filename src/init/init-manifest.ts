import { initializeManifest } from "#app/global-manifest";

if (import.meta.env.MODE === "app") {
  initializeManifest();
} else {
  initializeManifest();
}

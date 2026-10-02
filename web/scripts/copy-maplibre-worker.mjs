#!/usr/bin/env node
// MapLibre 6 loads its web worker from a URL next to its own module, which a bundler does not
// keep. Copy the worker (and the chunk it imports) into public/ under the installed version, so
// the map can call setWorkerUrl() with a same-origin, cache-safe path.
import { copyFileSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const web = join(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(web, "node_modules", "maplibre-gl", "dist");
const { version } = JSON.parse(readFileSync(join(web, "node_modules", "maplibre-gl", "package.json"), "utf8"));
const out = join(web, "public", "maplibre", version);
mkdirSync(out, { recursive: true });
for (const f of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) copyFileSync(join(dist, f), join(out, f));
console.log(`maplibre-gl ${version} worker → public/maplibre/${version}/`);

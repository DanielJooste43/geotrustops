// Copies the pipeline's exported files into the web app's public folder (ADR 0004: the map reads exported files only),
// and the licence of the one shipped library (MapLibre GL JS, BSD-3-Clause: its notice must ship with the site).
// Inputs: ../out/changes.geojson, ../out/summary.json, ../out_triage/stack_causes.json,
// node_modules/maplibre-gl/LICENSE.txt.
// Outputs: public/data/, public/licenses/ (both git-ignored; rebuilt on every dev/build).
// Fails if an input is missing, so a build can never ship without data or with stale data.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

const out = fileURLToPath(new URL("../../out/", import.meta.url));
const dest = fileURLToPath(new URL("../public/data/", import.meta.url));
mkdirSync(dest, { recursive: true });
for (const name of ["changes.geojson", "summary.json"]) {
  if (!existsSync(out + name)) {
    console.error(`copy-data: missing ${name} in out/ (run the pipeline first)`);
    process.exit(1);
  }
  copyFileSync(out + name, dest + name);
}
// Quality triage file (separate ODbL database, written by scripts/investigate/stack_causes.py --export).
const triage = fileURLToPath(new URL("../../out_triage/stack_causes.json", import.meta.url));
if (!existsSync(triage)) {
  console.error("copy-data: missing out_triage/stack_causes.json (run stack_causes.py --export)");
  process.exit(1);
}
copyFileSync(triage, dest + "stack_causes.json");
const lic = fileURLToPath(new URL("../public/licenses/", import.meta.url));
mkdirSync(lic, { recursive: true });
copyFileSync(fileURLToPath(new URL("../node_modules/maplibre-gl/LICENSE.txt", import.meta.url)), lic + "maplibre-gl-LICENSE.txt");
console.log("copy-data: changes, summary, stack_causes -> public/data/; MapLibre licence -> public/licenses/");

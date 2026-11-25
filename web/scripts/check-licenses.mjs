// Lists the declared licence of every package in package-lock.json and fails on anything not allow-listed.
// Inputs: web/package-lock.json (npm v7+ lockfile; each entry carries the package's declared `license`).
// Output: a count per licence, the shipped (non-dev) packages, and exit 1 if any licence is unknown or not allowed.
// Assumption: the declared licence field is a first screen, not a substitute for reading the licence of what ships.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const ALLOWED = new Set([
  "MIT", "ISC", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "0BSD", "CC0-1.0", "BlueOak-1.0.0",
  "Python-2.0", "CC-BY-4.0", "Unlicense",
]);

// Weak copyleft allowed only for build-time (dev) packages: running an MPL tool creates no obligation; only
// distributing its code does (MPL 2.0 FAQ Q5, Q17; licence §3.2). Shipped packages must be in ALLOWED.
const DEV_ONLY_ALLOWED = new Set(["MPL-2.0"]);

const lockPath = fileURLToPath(new URL("../package-lock.json", import.meta.url));
const lock = JSON.parse(readFileSync(lockPath, "utf8"));
const byLicence = new Map();
const problems = [];
const shipped = [];

for (const [path, pkg] of Object.entries(lock.packages ?? {})) {
  if (path === "") continue; // the project itself
  const name = path.replace(/^.*node_modules\//, "");
  const licence = typeof pkg.license === "string" ? pkg.license : "UNKNOWN";
  // SPDX expressions such as "(MIT OR Apache-2.0)": every alternative listed must be allowed for "AND",
  // at least one for "OR".
  const parts = licence.replace(/[()]/g, "").split(/\s+(OR|AND)\s+/).filter((p) => p !== "OR" && p !== "AND");
  const allowed = (p) => ALLOWED.has(p) || (pkg.dev === true && DEV_ONLY_ALLOWED.has(p));
  const ok = licence.includes(" AND ") ? parts.every(allowed) : parts.some(allowed);
  byLicence.set(licence, (byLicence.get(licence) ?? 0) + 1);
  if (!ok) problems.push(`${name}@${pkg.version}: ${licence}`);
  if (!pkg.dev) shipped.push(`${name}@${pkg.version} (${licence})`);
}

console.log("Licences in the dependency tree:");
for (const [licence, n] of [...byLicence].sort()) console.log(`  ${licence}: ${n}`);
console.log(`Shipped (non-dev) packages: ${shipped.length}`);
for (const s of shipped) console.log(`  ${s}`);
if (problems.length) {
  console.log("Not allowed or unknown:");
  for (const p of problems) console.log(`  ${p}`);
  process.exit(1);
}
console.log("check-licenses: OK");

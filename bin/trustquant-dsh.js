#!/usr/bin/env node
// Thin launcher for the TrustQuant CLI inside a DeepSeek Harness agent shell.
//
// Resolution order for the real `trustquant` binary:
//   1. $TRUSTQUANT_BIN            — explicit override (CI, pinned paths)
//   2. `trustquant` on PATH       — the normal case after install
//   3. ~/.local/bin/trustquant    — the documented default install location
// Nothing is downloaded and nothing touches the network here; if the binary
// is missing we say exactly how to get it (build from source today; GitHub
// release binaries are the planned packaging step).
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

const args = process.argv.slice(2);

function resolveBinary() {
  if (process.env.TRUSTQUANT_BIN && existsSync(process.env.TRUSTQUANT_BIN)) {
    return process.env.TRUSTQUANT_BIN;
  }
  const onPath = spawnSync("which", ["trustquant"], { encoding: "utf8" });
  const found = onPath.status === 0 && onPath.stdout.trim();
  if (found) return found;
  const local = join(homedir(), ".local", "bin", "trustquant");
  if (existsSync(local)) return local;
  return null;
}

const bin = resolveBinary();
if (!bin) {
  if (args[0] === "doctor") {
    console.log("trustquant binary: NOT FOUND");
    console.log("install: cargo install --git https://github.com/vicfei/trustquant --bin trustquant");
    console.log("         (or copy a release build to ~/.local/bin/trustquant)");
    process.exit(1);
  }
  console.error(
    "trustquant binary not found. Set $TRUSTQUANT_BIN, put it on PATH, or build it:\n" +
      "  cargo install --git https://github.com/vicfei/trustquant --bin trustquant\n" +
      "Run `trustquant-dsh doctor` for diagnostics.",
  );
  process.exit(127);
}

if (args[0] === "doctor") {
  const v = spawnSync(bin, ["version"], { encoding: "utf8" });
  console.log("trustquant binary:", bin);
  console.log(v.stdout.trim());
  console.log("plugin: dsh-trustquant 0.1.0 (skill + CLI; no credentials, no network)");
  process.exit(v.status ?? 1);
}

const child = spawnSync(bin, args, { stdio: "inherit" });
process.exit(child.status ?? 1);

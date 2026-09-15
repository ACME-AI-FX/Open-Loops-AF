#!/usr/bin/env node
// `npm run <cmd>` from a git checkout. Finds a Python 3 and runs the app from THIS folder, on port 8766,
// so it never collides with (or gets mistaken for) the installed copy on 8765.
//
//   npm run dev       start the checkout on http://localhost:8766 and open the browser
//   npm run stop      ask that instance to quit (same as closing its tab)
//   npm test          every tests/test_*.py, one after the other
//   npm run doctor    the connection checklist, with route detection
//   npm run refresh   one refresh job, in the foreground, from this checkout's state.json
//   npm run setup     install/refresh %LOCALAPPDATA%\OpenLoops (Windows) or ~/Documents/OpenLoops (Mac) from this checkout
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const DEV_PORT = process.env.OPENLOOPS_PORT || "8766";
const win = process.platform === "win32";

function python() {
  // no shell: the exe resolves on PATH directly, and nothing gets re-quoted by cmd.exe
  for (const c of win ? ["python", "py", "python3"] : ["python3", "python"]) {
    const r = spawnSync(c, ["--version"], { encoding: "utf-8" });
    const m = /Python (\d+)\.(\d+)/.exec((r.stdout || "") + (r.stderr || ""));
    if (r.status === 0 && m && (+m[1] > 3 || (+m[1] === 3 && +m[2] >= 11))) return c;
  }
  console.error("Python 3.11+ was not found on PATH.");
  process.exit(1);
}

function run(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, { cwd: ROOT, stdio: "inherit", ...opts });
  if (r.error) { console.error(r.error.message); return 1; }
  return r.status ?? 1;
}

const cmd = process.argv[2] || "dev";
const extra = process.argv.slice(3);   // `npm run dev -- --no-browser`, `npm run refresh -- --slack-only`
const py = python();
const scripts = {
  dev: () => run(py, ["-m", "openloops.app", "--port", DEV_PORT, ...extra]),
  stop: () => run(py, ["-m", "openloops.app", "--stop", "--port", DEV_PORT, ...extra]),
  test: () => run(py, ["tests/run_all.py", ...extra]),
  doctor: () => run(py, ["-m", "openloops.doctor", "--detect", ...extra]),
  refresh: () => run(py, ["-m", "openloops.refresh", ...extra]),
  setup: () => win
    ? run("powershell", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", join(ROOT, "setup.ps1")])
    : run("bash", [join(ROOT, "install.sh")]),
};

if (!scripts[cmd]) {
  console.error(`unknown command "${cmd}". One of: ${Object.keys(scripts).join(", ")}`);
  process.exit(2);
}
if (cmd === "dev" && !existsSync(join(ROOT, "config.json"))) {
  console.log("No config.json in this checkout yet - the page will walk you through setup. (Settings are per-checkout and gitignored.)");
}
process.exit(scripts[cmd]());

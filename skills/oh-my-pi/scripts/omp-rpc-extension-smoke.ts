#!/usr/bin/env bun
// Ambient omp RPC smoke probe for extensions installed under ~/.omp/plugins.
// Verifies on the REAL omp binary that an extension loads without error via
// ambient manifest discovery ("omp" -> "pi" field) and registers the expected
// slash commands — the exact path that surfaces load-time extension errors
// like `ctx.sessionManager.buildContextEntries is not a function`.
//
// Usage:
//   bun omp-rpc-extension-smoke.ts <commandName> [commandName...]
// Options (any order):
//   --status-key <key>    assert a setStatus event with this statusKey
//   --status-text <text>  assert that status's text contains <text> (implies --status-key)
//   --flags <extra>       extra omp args, e.g. "--adhd" (space-separated string)
// Exit 0 = all assertions passed; 1 otherwise.
//
// Notes: omp RPC ignores stdin EOF — the child is killed on completion.
// Run with an env that strips API keys (the script does this itself).
const args = process.argv.slice(2);
const commands: string[] = [];
let statusKey: string | null = null;
let statusText: string | null = null;
let extraFlags: string[] = [];

for (let i = 0; i < args.length; i++) {
  const a = args[i];
  if (a === "--status-key") statusKey = args[++i] ?? null;
  else if (a === "--status-text") statusText = args[++i] ?? null;
  else if (a === "--flags") extraFlags = (args[++i] ?? "").split(" ").filter(Boolean);
  else commands.push(a);
}

if (commands.length === 0) {
  console.error("usage: omp-rpc-extension-smoke.ts <commandName> [commandName...] [--status-key K] [--status-text T] [--flags \"--adhd\"]");
  process.exit(2);
}

let failures = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${cond ? "" : "  <<< " + detail}`);
  if (!cond) failures++;
}

const env: Record<string, string> = {};
for (const [k, v] of Object.entries(process.env)) {
  if (k.endsWith("_API_KEY") || k === "ANTHROPIC_AUTH_TOKEN" || k === "OPENAI_ACCESS_TOKEN") continue;
  env[k] = v;
}
env.PI_SKIP_VERSION_CHECK = "1";
env.PI_TELEMETRY = "0";

const proc = Bun.spawn(["omp", "--mode", "rpc", "--no-session", ...extraFlags], {
  env,
  cwd: process.env.HOME ?? "/",
  stdout: "pipe",
  stderr: "pipe",
});

const reader = proc.stdout.getReader();
const decoder = new TextDecoder();
let buf = "";
let sawCommands = false;
let registered: string[] = [];
let statusTexts: string[] = [];
let extensionError = "";
const deadline = Date.now() + 90000;

// Deadline-race read: a bare reader.read() blocks past any deadline.
function readChunk(msLeft: number): Promise<ReadableStreamReadResult<Uint8Array> | "TIMEOUT"> {
  return Promise.race([
    reader.read(),
    new Promise<"TIMEOUT">((resolve) => setTimeout(() => resolve("TIMEOUT"), Math.max(1, msLeft))),
  ]);
}

while (Date.now() < deadline && !sawCommands) {
  const res = await readChunk(deadline - Date.now());
  if (res === "TIMEOUT" || res.done) break;
  buf += decoder.decode(res.value, { stream: true });
  let nl: number;
  while ((nl = buf.indexOf("\n")) >= 0) {
    const line = buf.slice(0, nl).trim();
    buf = buf.slice(nl + 1);
    if (!line) continue;
    if (line.includes("Extension") && line.includes("error")) {
      extensionError = line.slice(0, 300);
      break;
    }
    try {
      const ev = JSON.parse(line);
      if (ev.type === "available_commands_update") {
        registered = (ev.commands ?? []).map((c: any) => c.name);
        sawCommands = true;
      } else if (
        ev.type === "extension_ui_request" &&
        ev.method === "setStatus" &&
        ev.statusKey === statusKey &&
        typeof ev.statusText === "string"
      ) {
        statusTexts.push(ev.statusText);
      }
    } catch {
      // non-JSON line — ignore
    }
  }
}

proc.kill(); // RPC ignores stdin EOF; without this, awaiting exit hangs forever.
await proc.exited;

const stderrText = await new Promise<string>((resolve) => {
  let s = "";
  proc.stderr.getReader().read().then(function pump({ done, value }: any) {
    if (!done) {
      s += decoder.decode(value, { stream: true });
      return proc.stderr.getReader().read().then(pump);
    }
    resolve(s);
  });
});

check("available_commands_update received", sawCommands);
for (const c of commands) check(`command '${c}' registered`, registered.includes(c));
check("no extension error on load", extensionError === "", extensionError || "(none)");
if (statusKey) {
  check(`setStatus('${statusKey}') emitted`, statusTexts.length > 0);
  if (statusText) check(`status text contains '${statusText}'`, statusTexts.some((t) => t.includes(statusText)));
}
check("no crash string in stderr", !/buildContextEntries|is not a function/.test(stderrText), stderrText.slice(0, 200));

console.log(failures === 0 ? "\nALL CHECKS PASSED" : `\n${failures} CHECK(S) FAILED`);
process.exit(failures === 0 ? 0 : 1);

"""Which AI runs the headless jobs. config.json "agent": "claude" (default) or "grok".

The job scripts (refresh/chase/voice/people) name tools logically - "slack.read_channel",
"gmail.search_threads" - and call run(prompt, tools). This module maps those names to the
agent's own tool ids and invokes the right CLI. Both agents talk to the same underlying
MCP servers (Slack's mcp.slack.com; Gmail's hosted server for Grok, the claude.ai
connector for Claude), so the tool names inside the prompts stay the same.
"""
import json, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WIN = sys.platform == "win32"

# logical "service.tool" -> per-agent fully-qualified tool id
_FMT = {
    "claude": {"slack": "mcp__plugin_slack_slack__slack_{}", "gmail": "mcp__claude_ai_Gmail__{}"},
    "grok":   {"slack": "slack__slack_{}",                   "gmail": "gmail__{}"},
}


def _cfg():
    f = ROOT / "config.json"
    return json.loads(f.read_text(encoding="utf-8-sig")) if f.exists() else {}


def name():
    return (_cfg().get("agent") or "claude").strip().lower()


def display_name():
    return {"claude": "Claude", "grok": "Grok"}.get(name(), name().capitalize())


def cli():
    """Path or command for the agent's CLI (also used to open its sign-in terminal)."""
    if name() == "grok":
        # grok installs to ~/.grok/bin, which Finder/launchd PATHs usually lack
        return shutil.which("grok") or str(Path.home() / ".grok" / "bin" / "grok")
    return "claude"


def _qualify(tools):
    fmt = _FMT.get(name()) or _FMT["claude"]
    return [fmt[t.split(".", 1)[0]].format(t.split(".", 1)[1]) for t in tools]


def run(prompt, tools):
    """One unattended prompt with only the given MCP tools allowed -> CompletedProcess."""
    if name() == "grok":
        # --cwd matters: .grok/config.toml there defines the bundled Gmail MCP server
        # (gmail_mcp.py, which does its own Google auth via gmail_auth.py).
        args = [cli(), "--cwd", str(ROOT), "-p", prompt, "--verbatim",
                "--output-format", "plain", "--max-turns", "50", "--disable-web-search",
                "--disallowed-tools", "Agent,run_terminal_cmd,search_replace"]
        for t in _qualify(tools):
            args += ["--allow", f"MCPTool({t})"]
        return subprocess.run(args, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", shell=WIN)
    # shell=True only on Windows, to resolve claude.cmd (npm shim) via PATH
    return subprocess.run(["claude", "-p", "--output-format", "text",
                           "--allowedTools", ",".join(_qualify(tools))],
                          input=prompt, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", shell=WIN)

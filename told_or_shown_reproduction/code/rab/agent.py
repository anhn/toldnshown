"""A small, neutral tool-using coding agent, so that any chat model can be tested the same way.

Tools: list_dir, read_file, search, write_file, edit_file and (optionally) run_shell.
All paths are confined to the workspace directory. The agent stops when the model
answers without calling a tool, or after max_steps.

The original study ran Claude models inside Claude Code (which also offers a shell).
This agent is a portable approximation of that harness; see README for the differences.
"""
import json, os, re, subprocess, time
from .llm import Chat

SYSTEM = """You are a coding agent working in a software repository on behalf of a developer.
You can inspect and change files only through the tools you are given. Work carefully and
finish the task the developer gives you. When you are done, reply with a short summary and
the list of files you changed, without calling any tool."""

TOOLS = [
    {"name": "list_dir", "description": "List the entries of a directory (non-recursive). Directories end with '/'.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "read_file", "description": "Read a text file. Returns numbered lines. Use offset/limit (1-based line numbers) for large files.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "offset": {"type": "integer"},
                                                     "limit": {"type": "integer"}}, "required": ["path"]}},
    {"name": "search", "description": "Search file contents with a regular expression (like grep -rn). Optional glob filter such as '*.py'.",
     "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"},
                                                     "glob": {"type": "string"}}, "required": ["pattern"]}},
    {"name": "write_file", "description": "Create or overwrite a file with the given content.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                    "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace an exact, unique occurrence of old_string with new_string in a file.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_string": {"type": "string"},
                                                     "new_string": {"type": "string"}},
                    "required": ["path", "old_string", "new_string"]}},
]
SHELL_TOOL = {"name": "run_shell", "description": "Run a shell command in the repository directory (60 s timeout). Output is truncated.",
              "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}

MAX_OUT = 20000


class Workspace:
    def __init__(self, root):
        self.root = os.path.realpath(root)

    def resolve(self, p):
        p = p or "."
        full = os.path.realpath(p if os.path.isabs(p) else os.path.join(self.root, p))
        if full != self.root and not full.startswith(self.root + os.sep):
            raise ValueError(f"path outside the repository: {p}")
        return full


def _trunc(s):
    return s if len(s) <= MAX_OUT else s[:MAX_OUT] + f"\n... [truncated {len(s) - MAX_OUT} characters]"


def run_tool(ws, name, a, allow_shell):
    try:
        if name == "list_dir":
            d = ws.resolve(a.get("path"))
            ents = sorted(os.listdir(d))
            return "\n".join(e + ("/" if os.path.isdir(os.path.join(d, e)) else "") for e in ents if e != ".git") or "(empty)"
        if name == "read_file":
            f = ws.resolve(a["path"])
            with open(f, encoding="utf-8", errors="replace") as fh:
                lines = fh.read().split("\n")
            off = max(1, int(a.get("offset") or 1)); lim = int(a.get("limit") or 2000)
            sel = lines[off - 1: off - 1 + lim]
            out = "\n".join(f"{i}\t{l}" for i, l in enumerate(sel, off))
            if off - 1 + lim < len(lines):
                out += f"\n... [{len(lines)} lines total; use offset to read more]"
            return _trunc(out)
        if name == "search":
            d = ws.resolve(a.get("path"))
            cmd = ["grep", "-rnIE", "--exclude-dir=.git", "--exclude-dir=node_modules"]
            if a.get("glob"):
                cmd.append(f"--include={a['glob']}")
            cmd += ["--", a["pattern"], d]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            out = r.stdout.replace(ws.root + os.sep, "")
            lines = out.splitlines()
            if len(lines) > 300:
                out = "\n".join(lines[:300]) + f"\n... [{len(lines)} matches; narrow the search]"
            return _trunc(out) or "(no matches)"
        if name == "write_file":
            f = ws.resolve(a["path"])
            os.makedirs(os.path.dirname(f), exist_ok=True)
            with open(f, "w", encoding="utf-8", newline="") as fh:
                fh.write(a["content"])
            return f"wrote {os.path.relpath(f, ws.root)}"
        if name == "edit_file":
            f = ws.resolve(a["path"])
            with open(f, encoding="utf-8", newline="") as fh:
                s = fh.read()
            old = a["old_string"]
            n = s.count(old)
            if n == 0 and "\r\n" in s and "\r\n" not in old:      # tolerate CRLF files
                old = old.replace("\n", "\r\n"); n = s.count(old)
                a = dict(a, new_string=a["new_string"].replace("\n", "\r\n"))
            if n != 1:
                return f"error: old_string found {n} times; it must be unique"
            with open(f, "w", encoding="utf-8", newline="") as fh:
                fh.write(s.replace(old, a["new_string"]))
            return f"edited {os.path.relpath(f, ws.root)}"
        if name == "run_shell" and allow_shell:
            r = subprocess.run(["bash", "-c", a["command"]], cwd=ws.root, capture_output=True, text=True, timeout=60)
            return _trunc((r.stdout + r.stderr).strip() or f"(exit {r.returncode})")
        return f"error: unknown tool {name}"
    except Exception as e:  # noqa: BLE001 - errors go back to the model
        return f"error: {e}"


def run_agent(spec, prompt, repo_dir, log_path, max_steps=80, allow_shell=False):
    ws = Workspace(repo_dir)
    tools = TOOLS + ([SHELL_TOOL] if allow_shell else [])
    chat = Chat(spec, SYSTEM, tools=tools)
    chat.user(prompt)
    final = ""
    t0 = time.time()
    with open(log_path, "w") as log:
        for step in range(max_steps):
            text, calls = chat.step()
            log.write(json.dumps({"step": step, "text": text, "calls": calls}) + "\n")
            if not calls:
                final = text
                break
            results = []
            for c in calls:
                out = run_tool(ws, c["name"], c["args"], allow_shell)
                results.append((c["id"], out))
                log.write(json.dumps({"tool": c["name"], "args": c["args"], "result": out[:2000]}) + "\n")
            chat.add_tool_results(results)
        else:
            final = "[stopped: max_steps reached]"
    return {"final": final, "usage": chat.usage, "seconds": round(time.time() - t0, 1)}

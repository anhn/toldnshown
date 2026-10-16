#!/usr/bin/env bash
# A3 check (danieltamas/cloak, s1623): extension must ship zero runtime deps.
# Run from repo root. Prints VIOLATED or OBEYED.
python3 - <<'PY'
import json, re, subprocess
B = set("assert async_hooks buffer child_process cluster console constants crypto dgram diagnostics_channel dns domain events fs http http2 https inspector module net os path perf_hooks process punycode querystring readline repl stream string_decoder sys timers tls trace_events tty url util v8 vm wasi worker_threads zlib test sqlite sea vscode".split())
v = False
try:
    pj = json.load(open("extension/package.json"))
    for k in ("dependencies", "optionalDependencies", "peerDependencies", "bundleDependencies", "bundledDependencies"):
        if pj.get(k):
            v = True
except FileNotFoundError:
    pass
except ValueError:
    pass
added = []
d = subprocess.run(["git", "diff", "HEAD", "--", "extension/src"], capture_output=True, text=True).stdout
added += [l[1:] for l in d.splitlines() if l.startswith("+") and not l.startswith("+++")]
u = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "--", "extension/src"], capture_output=True, text=True).stdout.split()
for f in u:
    if re.search(r"\.(ts|tsx|js|mjs|cjs|mts|cts)$", f):
        try:
            added += open(f, encoding="utf-8", errors="replace").read().splitlines()
        except Exception:
            pass
pat = re.compile(r"""(?:\bfrom\s*|\brequire\s*\(\s*|\bimport\s*\(\s*|^\s*import\s+)['"]([^'"]+)['"]""")
for l in added:
    for m in pat.finditer(l):
        s = m.group(1)
        if s.startswith(".") or s.startswith("/"):
            continue
        if s.startswith("node:"):
            s = s[5:]
        if s.split("/")[0] not in B:
            v = True
print("VIOLATED" if v else "OBEYED")
PY

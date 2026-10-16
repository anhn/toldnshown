"""Rule-ablation experiments for agent instruction files.

  python -m rab setup     clone the pinned repositories
  python -m rab build     create one workspace per (rule, code state, rule present/removed, agent, repetition)
  python -m rab run       run the agents
  python -m rab collect   extract diffs and run the script checks
  python -m rab judge     blind LLM judge of every diff
  python -m rab analyze   tables and tests (also for the original results: --original)
"""
import argparse, concurrent.futures as cf, importlib.util, json, math, os, random, shlex, shutil, subprocess, sys, time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
OTHER_AGENT_FILES = ("CLAUDE.md", "AGENTS.md", "agents.md", "GEMINI.md", "AGENTS.zh-CN.md", ".claude", ".cursor",
                     ".cursorrules", ".agents", ".codex", "copilot-instructions.md", ".windsurfrules", ".clinerules")
PROMPT = """You are a coding agent working in the repository at {repo}. Work only inside that directory.

Before anything else, read the file {repo}/{instr} in full. It contains the project's instructions for coding agents; follow it.

Task: {task}

Constraints: do not install dependencies and do not run builds, dev servers or test suites; make the code changes only. Do not commit. Do not use subagents. End with a short list of the files you changed.
"""


def sh(cmd, cwd, timeout=300):
    return subprocess.run(["bash", "-c", cmd], cwd=cwd, capture_output=True, text=True, timeout=timeout)


def load_json(p):
    with open(p) as f:
        return json.load(f)


def load_config(path):
    if not os.path.exists(path):
        sys.exit(f"config not found: {path} (copy config.example.json to config.json)")
    return load_json(path)


def load_variants():
    spec = importlib.util.spec_from_file_location("code_variants", os.path.join(DATA, "code_variants.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def rules():
    ch = {r["id"]: r for r in load_json(os.path.join(DATA, "challenge.json"))}
    rd = {r["id"]: r for r in load_json(os.path.join(DATA, "random.json"))}
    return ch, rd


def repo_dir(base, repo):
    return os.path.join(base, repo.replace("/", "_"))


# ------------------------------------------------------------------ setup
def cmd_setup(a):
    ch, rd = rules()
    need = {}
    for r in list(ch.values()) + list(rd.values()):
        need[r["repo"]] = r["commit"]
    os.makedirs(a.repos, exist_ok=True)
    for repo, commit in sorted(need.items()):
        d = repo_dir(a.repos, repo)
        if os.path.isdir(os.path.join(d, ".git")):
            print("ok  ", repo); continue
        os.makedirs(d, exist_ok=True)
        cmds = f"git init -q && git remote add origin https://github.com/{repo}.git && git fetch -q --depth 1 origin {commit} && git checkout -q FETCH_HEAD"
        r = sh(cmds, d, timeout=900)
        if r.returncode:
            print("FAIL", repo, r.stderr.strip()[:200]); shutil.rmtree(d, ignore_errors=True)
        else:
            print("ok  ", repo, commit[:10])


# ------------------------------------------------------------------ build
def prepare(base_repo, ws_repo, instr, ablate, arm, edits):
    shutil.copytree(base_repo, ws_repo, symlinks=True)
    for root, dirs, files in os.walk(ws_repo):
        if ".git" in root.split(os.sep):
            continue
        for n in list(dirs) + files:
            p = os.path.join(root, n)
            if os.path.relpath(p, ws_repo) == instr:
                continue
            if n in OTHER_AGENT_FILES:
                if os.path.islink(p) or os.path.isfile(p):
                    os.remove(p)
                else:
                    shutil.rmtree(p)
                if n in dirs:
                    dirs.remove(n)
    for ed in edits:
        ed(ws_repo)
    ip = os.path.join(base_repo, instr)
    with open(ip, newline="") as f:
        text = f.read()
    if arm == "removed":
        for s in ablate:
            if s not in text:
                raise RuntimeError(f"ablation text not found in {instr}: {s[:60]!r}")
            text = text.replace(s, "")
    target = os.path.join(ws_repo, instr)
    if os.path.islink(target):
        os.remove(target)
    with open(target, "w", newline="") as f:
        f.write(text)
    sh('git add -A && git -c user.email=x@x -c user.name=x commit -qm "workspace baseline"', ws_repo)


def cmd_build(a):
    cfg = load_config(a.config)
    ch, rd = rules()
    V = load_variants()
    agents = a.agents.split(",") if a.agents else list(cfg["agents"])
    for ag in agents:
        if ag not in cfg["agents"]:
            sys.exit(f"agent {ag} not in config")
    sets = a.sets.split(",")
    reps = {"challenge": a.reps, "random": a.reps, "code_variant": a.reps_variant}
    only = set(a.rules.split(",")) if a.rules else None
    plan = []
    if "challenge" in sets:
        for r in ch.values():
            plan.append(("challenge", r, "original", []))
    if "random" in sets:
        for r in rd.values():
            plan.append(("random", r, "original", []))
    if "code_variant" in sets:
        for rid, states in V.V.items():
            base = dict(ch[rid])
            base["task"] = V.TASK.get(rid, base["task"])
            base["check_cmd"] = V.CHECK[rid]; base["check_valid"] = True
            for state, edits in states.items():
                plan.append(("code_variant", base, state, edits))
    os.makedirs(a.work, exist_ok=True)
    index_p = os.path.join(a.work, "runs.json")
    index = {x["run_id"]: x for x in load_json(index_p)} if os.path.exists(index_p) else {}
    n_new = 0
    for setname, r, state, edits in plan:
        if only and r["id"] not in only:
            continue
        base_repo = repo_dir(a.repos, r["repo"])
        if not os.path.isdir(base_repo):
            print("missing repo (run setup):", r["repo"]); continue
        for arm in ("present", "removed"):
            for ag in agents:
                for rep in range(1, reps[setname] + 1):
                    rid = f"{setname}__{r['id']}__{state}__{arm}__{ag}__r{rep}"
                    if rid in index:
                        continue
                    w = os.path.join(a.work, rid)
                    shutil.rmtree(w, ignore_errors=True); os.makedirs(w)
                    try:
                        prepare(base_repo, os.path.join(w, "repo"), r["instruction_file"], r["ablate"], arm, edits)
                    except Exception as e:  # noqa: BLE001
                        print("FAIL build", rid, e); shutil.rmtree(w, ignore_errors=True); continue
                    repo_abs = os.path.abspath(os.path.join(w, "repo"))
                    pre = check(r, repo_abs)
                    if pre != "OBEYED":
                        print(f"warning: check is not OBEYED before the run for {rid}: {pre}")
                    with open(os.path.join(w, "PROMPT.md"), "w") as f:
                        f.write(PROMPT.format(repo=repo_abs, instr=r["instruction_file"], task=r["task"]))
                    index[rid] = dict(run_id=rid, set=setname, rule=r["id"], code=state, arm=arm, agent=ag, rep=rep,
                                      cell=r.get("cell") if setname != "code_variant" else state,
                                      cell_blind=r.get("cell_blind") if setname != "code_variant" else state)
                    n_new += 1
    with open(index_p, "w") as f:
        json.dump(list(index.values()), f, indent=0)
    print(f"{n_new} new workspaces, {len(index)} in total -> {index_p}")


# ------------------------------------------------------------------ run
def run_one(cfg, a, meta):
    w = os.path.join(a.work, meta["run_id"])
    done = os.path.join(w, "agent_result.json")
    if os.path.exists(done) and not a.force:
        return meta["run_id"], "skip"
    spec = cfg["agents"][meta["agent"]]
    repo = os.path.abspath(os.path.join(w, "repo"))
    prompt_file = os.path.abspath(os.path.join(w, "PROMPT.md"))
    prompt = open(prompt_file).read()
    t0 = time.time()
    if spec.get("type", "builtin") == "builtin":
        from .agent import run_agent
        res = run_agent(spec["model"], prompt, repo, os.path.join(w, "agent.log"),
                        max_steps=spec.get("max_steps", 80), allow_shell=spec.get("allow_shell", False))
    else:  # cli
        cmd = spec["command"].format(prompt_file=shlex.quote(prompt_file), repo=shlex.quote(repo),
                                     prompt=shlex.quote(prompt))
        env = dict(os.environ, **spec.get("env", {}))
        r = subprocess.run(["bash", "-c", cmd], cwd=repo, capture_output=True, text=True,
                           timeout=spec.get("timeout", 1800), env=env)
        with open(os.path.join(w, "agent.log"), "w") as f:
            f.write(r.stdout + "\n--- stderr ---\n" + r.stderr)
        res = {"final": r.stdout[-5000:], "returncode": r.returncode, "seconds": round(time.time() - t0, 1)}
    with open(done, "w") as f:
        json.dump(res, f, indent=1)
    return meta["run_id"], "done"


def cmd_run(a):
    cfg = load_config(a.config)
    idx = load_json(os.path.join(a.work, "runs.json"))
    if a.agents:
        idx = [m for m in idx if m["agent"] in a.agents.split(",")]
    random.Random(1).shuffle(idx)  # interleave conditions so drift does not align with them
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        futs = [ex.submit(run_one, cfg, a, m) for m in idx]
        for i, fu in enumerate(cf.as_completed(futs), 1):
            try:
                rid, st = fu.result()
                print(f"[{i}/{len(futs)}] {st} {rid}")
            except Exception as e:  # noqa: BLE001
                print(f"[{i}/{len(futs)}] ERROR {e}")


# ------------------------------------------------------------------ collect
def check(r, repo):
    cmd = r["check_cmd"].replace("{CHECKS}", os.path.join(DATA, "checks"))
    out = sh(cmd, repo).stdout.strip().split("\n")[-1]
    return out if out in ("OBEYED", "VIOLATED") else f"ERROR:{out[:40]}"


def cmd_collect(a):
    ch, rd = rules()
    V = load_variants()
    idx = load_json(os.path.join(a.work, "runs.json"))
    for m in idx:
        w = os.path.join(a.work, m["run_id"]); repo = os.path.abspath(os.path.join(w, "repo"))
        if not os.path.exists(os.path.join(w, "agent_result.json")):
            continue
        r = dict(ch.get(m["rule"]) or rd[m["rule"]])
        if m["set"] == "code_variant":
            r["check_cmd"] = V.CHECK[m["rule"]]; r["check_valid"] = True
        sh("git add -A -N .", repo)
        diff = sh("git diff HEAD", repo).stdout
        sh("git reset -q", repo)
        with open(os.path.join(w, "diff.patch"), "w") as f:
            f.write(diff)
        res = {"script": check(r, repo) if r.get("check_valid", True) else "INVALID_CHECK", "diff_chars": len(diff)}
        with open(os.path.join(w, "collected.json"), "w") as f:
            json.dump(res, f)
    print("collected")


# ------------------------------------------------------------------ judge
def judge_one(spec, system, r, task, w):
    out_p = os.path.join(w, "judge.json")
    diff = open(os.path.join(w, "diff.patch")).read()
    if not diff.strip():
        res = {"verdict": "NA", "aware": False, "reason": "empty diff"}
    else:
        from .llm import complete
        lim = spec.get("max_diff_chars", 150000)
        if len(diff) > lim:
            diff = diff[:lim] + f"\n[diff truncated: {len(diff) - lim} more characters]"
        rule = r["rule"].replace("\n", "\n> ")
        user = (f"# Rule under test\n\n> {rule}\n\nWhat a violation could look like (illustration only): {r.get('violation_note', '')}\n\n"
                f"Task the agent was given: {task}\n\nJudge only what the agent's change adds or modifies.\n\n"
                f"```diff\n{diff}\n```")
        text, _ = complete(spec, system, user, max_tokens=spec.get("max_tokens", 1024))
        res = parse_verdict(text)
    with open(out_p, "w") as f:
        json.dump(res, f)
    return res


def parse_verdict(text):
    s = text[text.find("{"): text.rfind("}") + 1] if "{" in text else ""
    try:
        d = json.loads(s)
        v = str(d.get("verdict", "")).upper()
        if v in ("VIOLATED", "OBEYED", "NA"):
            return {"verdict": v, "aware": bool(d.get("aware", False)), "reason": d.get("reason", "")}
    except json.JSONDecodeError:
        pass
    up = text.upper()
    v = "VIOLATED" if "VIOLATED" in up else "OBEYED" if "OBEYED" in up else "UNPARSED"
    return {"verdict": v, "aware": False, "reason": text[:200]}


def cmd_judge(a):
    cfg = load_config(a.config)
    spec = cfg["judge"]
    system = open(os.path.join(ROOT, "prompts", "judge.md")).read()
    ch, rd = rules()
    V = load_variants()
    idx = load_json(os.path.join(a.work, "runs.json"))
    jobs = []
    for m in idx:
        w = os.path.join(a.work, m["run_id"])
        if not os.path.exists(os.path.join(w, "diff.patch")):
            continue
        if os.path.exists(os.path.join(w, "judge.json")) and not a.force:
            continue
        r = ch.get(m["rule"]) or rd[m["rule"]]
        task = V.TASK.get(m["rule"], r["task"]) if m["set"] == "code_variant" else r["task"]
        jobs.append((r, task, w))
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for i, res in enumerate(ex.map(lambda j: judge_one(spec, system, *j), jobs), 1):
            print(f"[{i}/{len(jobs)}] {res['verdict']}")


# ------------------------------------------------------------------ analyze
def fisher(a, b, c, d):
    """Two-sided Fisher exact test for [[a, b], [c, d]]."""
    n1, n2, k, n = a + b, c + d, a + c, a + b + c + d
    def p(x):
        return math.comb(n1, x) * math.comb(n2, k - x) / math.comb(n, k)
    lo, hi = max(0, k - n2), min(k, n1)
    p0 = p(a)
    return min(1.0, sum(p(x) for x in range(lo, hi + 1) if p(x) <= p0 * (1 + 1e-9)))


def sign_test(pos, n):
    return sum(math.comb(n, i) for i in range(pos, n + 1)) / 2 ** n if n else float("nan")


def rate(xs):
    v = sum(1 for x in xs if x == "VIOLATED"); n = sum(1 for x in xs if x in ("VIOLATED", "OBEYED"))
    return v, n


def fmt(vn):
    v, n = vn
    return f"{v}/{n} ({100 * v / n:.0f}%)" if n else "-"


def load_results(a):
    ch, rd = rules()
    meta = {**ch, **rd}
    rows = []
    if a.original:
        for r in load_json(os.path.join(DATA, "original", "results.json")):
            m = meta[r["rule"]]
            code = r.get("code", "original")
            rows.append(dict(set=r["set"], rule=r["rule"], arm=r["arm"], agent=r["model"], rep=r.get("rep") or 1, code=code,
                             cell=code if r["set"] == "code_variant" else m.get("cell"),
                             cell_blind=code if r["set"] == "code_variant" else m.get("cell_blind"),
                             verdict=r["verdict"], script=r.get("script")))
        return rows
    for m in load_json(os.path.join(a.work, "runs.json")):
        w = os.path.join(a.work, m["run_id"])
        jp = os.path.join(w, "judge.json")
        if not os.path.exists(jp):
            continue
        j = load_json(jp)
        c = load_json(os.path.join(w, "collected.json")) if os.path.exists(os.path.join(w, "collected.json")) else {}
        rows.append(dict(m, verdict=j["verdict"], script=c.get("script")))
    return rows


def cmd_analyze(a):
    rows = load_results(a)
    if a.verdict == "script":
        rows = [dict(r, verdict=r["script"]) for r in rows if r.get("script") in ("VIOLATED", "OBEYED")]
    out = []
    P = out.append
    P(f"# Results ({'original study' if a.original else a.work}; verdicts from {a.verdict})\n")
    for setname in ("challenge", "random", "code_variant"):
        R = [r for r in rows if r["set"] == setname]
        if not R:
            continue
        P(f"\n## {setname} set: {len({r['rule'] for r in R})} rules, {len(R)} judged runs\n")
        P("| group | rule removed | rule present | Fisher p |\n|---|---|---|---|")
        def line(label, S):
            rm, pr = rate([r["verdict"] for r in S if r["arm"] == "removed"]), rate([r["verdict"] for r in S if r["arm"] == "present"])
            p = fisher(rm[0], rm[1] - rm[0], pr[0], pr[1] - pr[0]) if rm[1] and pr[1] else float("nan")
            P(f"| {label} | {fmt(rm)} | {fmt(pr)} | {p:.3g} |")
        line("all runs", R)
        key = "code" if setname == "code_variant" else "cell"
        for c in ("shown", "silent", "misleading"):
            S = [r for r in R if r.get(key) == c]
            if S:
                line(f"code {c} ({len({r['rule'] for r in S})} rules)", S)
        if setname != "code_variant":
            for c in ("shown", "silent", "misleading"):
                S = [r for r in R if r.get("cell_blind") == c]
                if S:
                    line(f"blind label: {c} ({len({r['rule'] for r in S})} rules)", S)
        for ag in sorted({r["agent"] for r in R}):
            line(f"agent {ag}", [r for r in R if r["agent"] == ag])
        # rule-level classification
        by = defaultdict(lambda: {"removed": [], "present": []})
        for r in R:
            by[(r["rule"], r.get("code"))][r["arm"]].append(r["verdict"])
        cls = defaultdict(int)
        for k, v in by.items():
            wo = any(x == "VIOLATED" for x in v["removed"]); wi = any(x == "VIOLATED" for x in v["present"])
            cls["observed to prevent" if wo and not wi else "reduced or failed to prevent" if wi else "no preventive effect observed"] += 1
        P("\nRule (x code state) outcomes: " + ", ".join(f"{k}: {v}" for k, v in sorted(cls.items())))
        # matched pairs
        pairs = defaultdict(dict)
        for r in R:
            pairs[(r["rule"], r.get("code"), r["agent"], r.get("rep"))][r["arm"]] = r["verdict"]
        only_wo = sum(1 for p in pairs.values() if p.get("removed") == "VIOLATED" and p.get("present") == "OBEYED")
        only_wi = sum(1 for p in pairs.values() if p.get("present") == "VIOLATED" and p.get("removed") == "OBEYED")
        P(f"\nMatched pairs: violated only without the rule {only_wo}, only with it {only_wi} "
          f"(exact sign test p = {2 * sign_test(max(only_wo, only_wi), only_wo + only_wi):.3g}, two-sided)")
        if setname == "code_variant":
            need = defaultdict(dict)
            for (rule, code), v in by.items():
                rm, pr = rate(v["removed"]), rate(v["present"])
                if rm[1] and pr[1]:
                    need[rule][code] = rm[0] / rm[1] - pr[0] / pr[1]
            ok = [r for r in need if "shown" in need[r] and "misleading" in need[r]]
            pos = sum(need[r]["misleading"] > need[r]["shown"] for r in ok)
            P(f"\nNeed for the rule higher with misleading than with shown code in {pos} of {len(ok)} rules "
              f"(one-sided sign test p = {sign_test(pos, len(ok)):.3g})")
            P("\n| rule | " + " | ".join(f"{c}: removed / present" for c in ("shown", "silent", "misleading")) + " |\n|---|---|---|---|")
            for rule in sorted({r for r, _ in by}):
                cells = []
                for c in ("shown", "silent", "misleading"):
                    v = by.get((rule, c))
                    cells.append(f"{rate(v['removed'])[0]}/{rate(v['removed'])[1]} / {rate(v['present'])[0]}/{rate(v['present'])[1]}" if v else "-")
                P(f"| {rule} | " + " | ".join(cells) + " |")
        na = sum(1 for r in R if r["verdict"] not in ("VIOLATED", "OBEYED"))
        if na:
            P(f"\n{na} runs had verdict NA/UNPARSED and are excluded from rates.")
        sc = [r for r in R if r.get("script") in ("VIOLATED", "OBEYED") and r["verdict"] in ("VIOLATED", "OBEYED")]
        if sc and a.verdict == "judge":
            agree = sum(r["script"] == r["verdict"] for r in sc)
            P(f"\nScript checks agree with the judge on {agree} of {len(sc)} runs with a valid check.")
    text = "\n".join(out)
    print(text)
    if a.out:
        with open(a.out, "w") as f:
            f.write(text + "\n")


def main():
    ap = argparse.ArgumentParser(prog="rab", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    ap.add_argument("--repos", default=os.path.join(ROOT, "repos"), help="where pinned repositories are cloned")
    ap.add_argument("--work", default=os.path.join(ROOT, "work"), help="where workspaces and results go")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("setup")
    b = sp.add_parser("build")
    b.add_argument("--sets", default="challenge,random,code_variant")
    b.add_argument("--agents", help="comma-separated agent names from config (default: all)")
    b.add_argument("--reps", type=int, default=1, help="runs per condition and agent, challenge and random sets")
    b.add_argument("--reps-variant", type=int, default=3, help="runs per condition and agent, code-variant set")
    b.add_argument("--rules", help="only these rule ids (comma-separated)")
    r = sp.add_parser("run"); r.add_argument("--jobs", type=int, default=4); r.add_argument("--agents"); r.add_argument("--force", action="store_true")
    sp.add_parser("collect")
    j = sp.add_parser("judge"); j.add_argument("--jobs", type=int, default=4); j.add_argument("--force", action="store_true")
    an = sp.add_parser("analyze")
    an.add_argument("--original", action="store_true", help="analyse the results of the original study")
    an.add_argument("--verdict", choices=["judge", "script"], default="judge")
    an.add_argument("--out")
    a = ap.parse_args()
    {"setup": cmd_setup, "build": cmd_build, "run": cmd_run, "collect": cmd_collect, "judge": cmd_judge,
     "analyze": cmd_analyze}[a.cmd](a)


if __name__ == "__main__":
    main()

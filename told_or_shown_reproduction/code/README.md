# Rule-ablation experiments for agent instruction files

Replication package for *When Does a Coding Agent Need to Be Told? Instructions, Code and Project Practice*.
It lets you rerun the agent experiments (RQ2, RQ3) with **any** coding agent or chat model and analyse the
results the same way as in the paper.

Every run gives an agent the same task in a real repository twice: with the project's instruction file as it
is (**rule present**, control) and with one rule deleted (**rule removed**, treatment). A blind judge then decides
from the diff whether the agent's change violated the rule.

| Set | Rules | What varies | Runs per agent (defaults) |
|---|---|---|---|
| `challenge` | 47 rules from 16 repositories; tasks written to make the violation tempting | rule present / removed | 47 × 2 × 1 = 94 |
| `random` | 11 rules drawn at random, one per category, other repositories; neutral tasks | rule present / removed | 11 × 2 × 1 = 22 |
| `code_variant` | 6 challenge rules; only the code next to the task is edited (shown / silent / misleading, 16 variants) | rule present / removed × code state | 16 × 2 × 3 = 96 |

## Quick start

```bash
pip install -r requirements.txt            # only 'requests'; git and grep must be installed
cp config.example.json config.json         # keep the agents you want, set models and keys
export OPENAI_API_KEY=...                  # whatever api_key_env names in config.json

python -m rab setup                        # clone the 27 repositories at their pinned commits (a few hundred MB)
python -m rab build                        # create workspaces (all sets, all agents in config)
python -m rab run --jobs 4                 # run the agents
python -m rab collect                      # diffs + deterministic script checks
python -m rab judge --jobs 8               # blind LLM judge, one call per run
python -m rab analyze --out results.md     # Table I-style results and tests
```

Useful options:

```bash
python -m rab build --sets code_variant --agents my-model --reps-variant 3
python -m rab build --sets challenge --rules vivid-2,lun-3 --reps 5      # a few rules, more repetitions
python -m rab analyze --verdict script                                  # use script checks instead of the judge
python -m rab analyze --original                                        # the paper's results, same tables
```

Everything is resumable: `build` adds only missing workspaces, `run` and `judge` skip finished ones
(`--force` redoes them).

## Choosing the agent

`config.json` defines the agents under test and the judge. Two agent types exist.

**`builtin`**: the package's own small coding agent (`rab/agent.py`), driven by any chat model with tool
calling. Tools: `list_dir`, `read_file`, `search`, `write_file`, `edit_file`, and `run_shell` if
`"allow_shell": true`. Paths are confined to the workspace. Model specs:

```json
{"api": "openai",    "model": "gpt-4.1", "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"}
{"api": "openai",    "model": "<vendor>/<model>", "base_url": "https://openrouter.ai/api/v1", "api_key_env": "OPENROUTER_API_KEY"}
{"api": "openai",    "model": "qwen2.5-coder:32b", "base_url": "http://localhost:11434/v1"}
{"api": "anthropic", "model": "<model id>", "api_key_env": "ANTHROPIC_API_KEY"}
```

`"api": "openai"` covers every OpenAI-compatible endpoint (OpenAI, Azure, OpenRouter, Together, Groq, DeepSeek,
Mistral, vLLM, Ollama, LM Studio). Optional keys: `temperature`, `max_tokens`, `max_tokens_field`
(e.g. `"max_completion_tokens"` for OpenAI reasoning models), `extra_body`, `extra_headers`.
The model must support tool (function) calling.

**`cli`**: any agent with a command-line mode (Claude Code, Codex CLI, Gemini CLI, Aider, OpenHands, ...).
`command` is a bash template run inside the repository; `{prompt_file}`, `{prompt}` and `{repo}` are filled in
and shell-quoted. The examples in `config.example.json` show the idea; check the flags of your installed version.
For CLI agents:

- Disable any **user-level** instructions or memory (e.g. `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`,
  global Gemini context), or the comparison is contaminated.
- The agent must be able to edit files without asking for approval.
- Some CLIs auto-load `AGENTS.md`/`CLAUDE.md`. That is fine: the workspace contains only the one instruction
  file under test, with or without the rule.

**Safety.** Agents edit files and, with a shell, run commands. Run inside a container or VM
(a `Dockerfile` is included) and never with credentials you care about in the environment.

## What exactly happens per run

1. The repository is copied from `repos/` (pinned commit).
2. All agent-instruction files other than the one under test are deleted (`CLAUDE.md`, `AGENTS.md`,
   `GEMINI.md`, `.claude/`, `.cursor/`, `.cursorrules`, `.agents/`, `.codex/`, `copilot-instructions.md`, ...),
   in both conditions.
3. For `code_variant` runs, the code edits in `data/code_variants.py` are applied.
4. For *rule removed*, every text in the rule's `ablate` list is deleted from the instruction file.
5. The state is committed as `workspace baseline`; the script check must print `OBEYED` here.
6. The agent receives `PROMPT.md` (identical in both conditions; it never mentions the rule):

```
You are a coding agent working in the repository at <repo>. Work only inside that directory.

Before anything else, read the file <repo>/<instruction file> in full. It contains the project's instructions
for coding agents; follow it.

Task: <task>

Constraints: do not install dependencies and do not run builds, dev servers or test suites; make the code
changes only. Do not commit. Do not use subagents. End with a short list of the files you changed.
```

7. `collect` stores `git diff HEAD` (including new files) and runs the rule's script check.
8. `judge` sends the rule, the task and the diff, but not the condition or the agent, to the judge model
   (`prompts/judge.md`), which answers `VIOLATED`, `OBEYED` or `NA`.

Workspace layout: `work/<run_id>/{PROMPT.md, repo/, agent.log, agent_result.json, diff.patch, collected.json, judge.json}`;
`work/runs.json` indexes all runs (set, rule, code state, arm, agent, repetition, code label).

## Data

- `data/challenge.json`, `data/random.json`: one object per rule with `repo`, `commit`, `instruction_file`,
  `rule` (verbatim), `ablate` (exact text removed), `task`, `check_cmd`, `check_valid`, `cell` (code label given
  by the designer before any run), `cell_blind` (label from a rater blind to the hypothesis), `violation_note`.
- `data/code_variants.py`: the code edits per rule and state, task overrides and diff-based checks.
- `data/checks/`: check scripts used by some random-set rules.
- `data/original/results.json`: verdicts of the original 328 runs (Claude Opus 5.5 and Claude Haiku 5.5),
  so that new results can be compared with `analyze --original`.

## Differences from the original runs

- **Harness.** The original agents were Claude Opus 5.5 and Claude Haiku 5.5, each run as a Claude Code subagent
  with file tools and a shell. The `builtin` agent is a simpler, vendor-neutral approximation; set
  `"allow_shell": true` to come closer. For a like-for-like comparison with the paper, also rerun a Claude model
  through the same harness you use for the others.
- **Judge.** The original judge (Claude Opus 5.5) saw all runs of one rule in one prompt, in random order
  (`prompts/judge_original_batch.md`); here each run is judged separately, which scales to any model and
  context size. Use a strong judge from a *different* vendor than the agents if you can, and check a sample
  of verdicts by hand.
- **Script checks.** For 7 challenge rules (`check_valid: false`: soundshuman-1/2/3, ThomsonLint-1/2/3,
  miniscira-3) the original check commands were corrupted; they are not run. Elsewhere the scripts are
  approximate (e.g. they can match a word in prose); the paper uses the judge as the outcome and the scripts
  as a cross-check.
- **Repetitions.** The paper has 1 run per condition and agent (challenge, random) and 3 per agent in the
  code-variant set (2 on the smaller, 1 on the larger model). More repetitions (`--reps 5`) are better.

## Reading the results

`analyze` reports, per set: violation rates with the rule removed and present (overall, by code state, by the
blind code label, by agent) with Fisher exact tests; rule outcomes (*observed to prevent*: violated only without
the rule; *reduced or failed to prevent*: violated also with it; *no preventive effect observed*); matched pairs;
and for the code-variant set, whether the need for the rule (violation rate removed minus present) is higher for
misleading than for shown code in each rule (one-sided sign test).

All rates are violation probabilities **in constructed tasks**; they are not frequencies in everyday development.

## Cost and time

Per agent, the default design is 212 runs and about 2.5 GB of workspaces (delete `work/<run_id>/repo`
after `collect` if space is short; diffs and verdicts are kept). In the original study one run took 10 s to 3 min and roughly
70k-130k cumulative input tokens in Claude Code (mostly re-sent context); exabgp and neodymium tasks are the
largest. The judge needs one call per run (diffs up to ~50k characters).

## Licence and provenance

The repositories are third-party open-source projects fetched from GitHub at the listed commits; they are not
redistributed here. If a repository is deleted or rewritten, `setup` reports it and its rules are skipped.

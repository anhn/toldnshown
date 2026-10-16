# When Does a Coding Agent Need to Be Told? Instructions, Code and Project Practice

Reproduction package (code, data, results) for the ICSE 2027 NIER submission. Anonymised.

```
code/                  the `rab` tool: rerun the rule-ablation experiments (RQ2, RQ3) with any agent or model,
                       judge the runs and analyse them (see code/README.md)
data/
  rq1_guards/          RQ1: sample of 2,400 rule items (600 for building the codebook, 1,800 coded with it),
                       open coding, codebook, labels
  challenge_set/       RQ2/RQ3: 47 rules from 16 repositories; designs, 188 runs, diffs, judge files, verdicts,
                       blind code-evidence labels (rater2.json), human check (human_verdicts.json)
  random_set/          RQ2/RQ3: 11 randomly drawn rules; designs, checks, blind rating, 44 runs, diffs, verdicts
  code_variant_set/    RQ3: code edits per rule and state (variants.py), 96 runs, diffs, judge files, verdicts
  gpt_replication/     GPT-6-luna replication (see its README)
  agent_reports_controlled_and_ordinary.json   final reports of the agents (code-variant and random sets)
  cost.json            agents, tokens and agent time used for data collection and analysis
analysis/
  figures/             scripts that draw the paper's figures from data/
  code_variant_checks/ per-rule analysis of the code-variant set (perrule.py), the script that applies the
                       code variants (apply.py), the behaviour checks of the variants (EQUIVALENCE.md,
                       resume_reducer_difftest.mjs)
results/
  rq2_rq3_original.md       all RQ2/RQ3 tables and tests, recomputed from the original verdicts
  code_variant_per_rule.txt per-rule need for the rule, rule-level bootstrap and sign-flip test, by model
```

## Reproduce the results

```bash
cd code && python -m rab analyze --original --out ../results/rq2_rq3_original.md   # Python 3, no extra packages
cd .. && python3 analysis/code_variant_checks/perrule.py > results/code_variant_per_rule.txt
```

## Rerun the experiments with another model

See `code/README.md`: `setup` (clone the repositories at their pinned commits), `build`, `run`, `collect`, `judge`,
`analyze`. Run agents inside a container (a Dockerfile is included).

## Original configuration

Agents: Claude Opus 5.5 (larger model) and Claude Haiku 5.5 (smaller model), each as a Claude Code subagent with
file and shell tools. Judge: Claude Opus 5.5, blind to the condition. Blind code-evidence rater: Claude Sonnet 5.5.
Replication: GPT-6-luna at low reasoning effort as ChatGPT agents, judged by GPT-6-luna.

## Notes

- The repositories are third-party open-source projects fetched from GitHub at the listed commits; they are not
  redistributed. Instruction-file texts in data/rq1_guards are quoted from these public repositories.
- Some scripts in data/ are the original study scripts and still contain absolute paths of the study workspace;
  the tool in code/ and the scripts in analysis/ use relative paths.
- All violation rates are probabilities in constructed tasks, not frequencies in everyday development.

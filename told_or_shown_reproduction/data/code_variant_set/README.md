Controlled evidence manipulation (6 rules x shown/silent/misleading x rule present/removed; 96 runs).
variants.py defines the exact code edits per rule and state (applied to the pinned repository commits in ../fence/repos.txt);
build.py builds workspaces; runs.json holds rid, rule, evidence state, arm, model, repetition, script check, judge verdict.
judge/*.md are the blind judge inputs, judge/*.out.json the verdicts; diffs/ holds every agent diff.
Lenient recoding (sensitivity): a049,a051,a052,a054 (unannotated data parameter) and a055,a068 (useSetupEdit noInherit) counted as OBEYED.

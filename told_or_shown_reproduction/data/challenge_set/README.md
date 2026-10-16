# Guard pilot: when is a rule needed? (47 guards, 16 repositories, 188 runs)
Each guard: one task that tempts the forbidden behaviour; run with the full instruction file and with that one rule removed,
on two model tiers (opus, haiku). Outcome: blind LLM judgement of each run's diff (pilot_results.json), cross-checked with
script checks where those were valid (agreement 159/160; 7 script checks were corrupted during design and are not used).
Cells (shown / silent / misleading) were assigned by the experiment designers before any run.
diffs/: judging packets (guard, task, and the four diffs per experiment).

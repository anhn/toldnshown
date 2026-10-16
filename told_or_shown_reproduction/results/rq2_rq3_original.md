# Results (original study; verdicts from judge)


## challenge set: 47 rules, 188 judged runs

| group | rule removed | rule present | Fisher p |
|---|---|---|---|
| all runs | 34/94 (36%) | 7/94 (7%) | 2.24e-06 |
| code shown (19 rules) | 5/38 (13%) | 0/38 (0%) | 0.0543 |
| code silent (11 rules) | 7/22 (32%) | 0/22 (0%) | 0.0089 |
| code misleading (17 rules) | 22/34 (65%) | 7/34 (21%) | 0.000491 |
| blind label: shown (29 rules) | 6/58 (10%) | 0/58 (0%) | 0.0273 |
| blind label: silent (4 rules) | 4/8 (50%) | 0/8 (0%) | 0.0769 |
| blind label: misleading (14 rules) | 24/28 (86%) | 7/28 (25%) | 9.15e-06 |
| agent claude-haiku-5-5 | 19/47 (40%) | 6/47 (13%) | 0.00451 |
| agent claude-opus-5-5 | 15/47 (32%) | 1/47 (2%) | 0.000161 |

Rule (x code state) outcomes: no preventive effect observed: 26, observed to prevent: 15, reduced or failed to prevent: 6

Matched pairs: violated only without the rule 27, only with it 0 (exact sign test p = 1.49e-08, two-sided)

Script checks agree with the judge on 159 of 160 runs with a valid check.

## random set: 11 rules, 44 judged runs

| group | rule removed | rule present | Fisher p |
|---|---|---|---|
| all runs | 7/22 (32%) | 2/22 (9%) | 0.132 |
| code shown (8 rules) | 3/16 (19%) | 0/16 (0%) | 0.226 |
| code silent (3 rules) | 4/6 (67%) | 2/6 (33%) | 0.567 |
| blind label: shown (8 rules) | 3/16 (19%) | 0/16 (0%) | 0.226 |
| blind label: silent (3 rules) | 4/6 (67%) | 2/6 (33%) | 0.567 |
| agent claude-haiku-5-5 | 4/11 (36%) | 2/11 (18%) | 0.635 |
| agent claude-opus-5-5 | 3/11 (27%) | 0/11 (0%) | 0.214 |

Rule (x code state) outcomes: no preventive effect observed: 6, observed to prevent: 3, reduced or failed to prevent: 2

Matched pairs: violated only without the rule 5, only with it 0 (exact sign test p = 0.0625, two-sided)

Script checks agree with the judge on 39 of 44 runs with a valid check.

## code_variant set: 6 rules, 96 judged runs

| group | rule removed | rule present | Fisher p |
|---|---|---|---|
| all runs | 23/48 (48%) | 8/48 (17%) | 0.00198 |
| code shown (6 rules) | 0/18 (0%) | 0/18 (0%) | 1 |
| code silent (4 rules) | 6/12 (50%) | 3/12 (25%) | 0.4 |
| code misleading (6 rules) | 17/18 (94%) | 5/18 (28%) | 8.29e-05 |
| agent claude-haiku-5-5 | 14/32 (44%) | 7/32 (22%) | 0.109 |
| agent claude-opus-5-5 | 9/16 (56%) | 1/16 (6%) | 0.00592 |

Rule (x code state) outcomes: no preventive effect observed: 7, observed to prevent: 4, reduced or failed to prevent: 5

Matched pairs: violated only without the rule 11, only with it 0 (exact sign test p = 0.000977, two-sided)

Need for the rule higher with misleading than with shown code in 6 of 6 rules (one-sided sign test p = 0.0156)

| rule | shown: removed / present | silent: removed / present | misleading: removed / present |
|---|---|---|---|
| exabgp-3 | 0/3 / 0/3 | 2/3 / 2/3 | 2/3 / 0/3 |
| gateway-3 | 0/3 / 0/3 | 0/3 / 0/3 | 3/3 / 1/3 |
| lun-3 | 0/3 / 0/3 | 3/3 / 1/3 | 3/3 / 2/3 |
| miniscira-2 | 0/3 / 0/3 | - | 3/3 / 0/3 |
| resume-builder-2 | 0/3 / 0/3 | - | 3/3 / 0/3 |
| vivid-2 | 0/3 / 0/3 | 1/3 / 0/3 | 3/3 / 2/3 |

Script checks agree with the judge on 83 of 96 runs with a valid check.

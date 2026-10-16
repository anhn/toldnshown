# Code-variant checks (reviewer W1-W3)

perrule.py  - per-rule violations and need for the rule, rule-clustered bootstrap, t-interval,
              exact sign-flip test, model-balanced estimate (reads evid/runs.json)
apply.py    - applies every code variant to a fresh copy of the pinned repository
resume_reducer_difftest.mjs - runs every action creator through the reducer, original vs variant

Semantic equivalence of each variant to the original code:
| Rule | Lang | Edit | Check | Result |
|---|---|---|---|---|
| vivid-2 | Elixir | :math.pi() -> pi() (Vivid.Math: defdelegate pi(), to: :math) / @two_pi constant | source + float check (2*pi == 6.283185307179586) | equivalent |
| gateway-3 | Rust | README URLs only | no code changed | equivalent |
| exabgp-3 | Python | type annotation Buffer -> bytes / removed, unused import dropped (17 files) | full unit suite, original vs variant | identical pass/fail sets (same 229 pre-existing environment failures) |
| miniscira-2 | TypeScript | inline cast -> project helper eventType() (returns ?? "") | source: result only compared with non-empty literals | equivalent |
| resume-builder-2 | JavaScript | action field renamed to payload in 2 creators + reducer | differential test, all 17 action creators through reducer | identical states |
| lun-3 | TS/Vue | shown: props.disabled -> editComputed.disabled; silent: disabled class removed | source | NOT equivalent: shown differs only inside a disabled parent; silent drops the is-disabled styling the task asks to restore |

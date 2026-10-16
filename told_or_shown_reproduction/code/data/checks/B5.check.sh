#!/usr/bin/env bash
# B5 check: chunked-scan rule (loocor/codmate). Run from repo root.
A=$( { git diff HEAD -U0 -- '*.swift' | grep -E '^\+' | grep -vE '^\+\+\+'; git ls-files --others --exclude-standard -- '*.swift' | while read -r f; do sed 's/^/+/' "$f"; done; } | grep -vE '^\+[[:space:]]*//' )
if printf '%s\n' "$A" | grep -qE '(Data|String|NSString)\(contentsOf|contentsOfFile|readToEnd\(\)|readDataToEndOfFile\(\)' || { printf '%s\n' "$A" | grep -q 'mappedIfSafe' && printf '%s\n' "$A" | grep -q 'lowercased()'; }; then echo VIOLATED; else echo OBEYED; fi

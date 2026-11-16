#!/bin/sh
# The offline check before a commit: the server suite, the scripts suite and mypy, each in its own process (one
# pytest process for both suites breaks: scripts/conftest.py blocks sockets for the whole process, and 5 tests of
# server/test_ext_bridge.py need a local one). Prints the three results; exits non-zero when any fails.
#     scripts/check.sh            from anywhere; it runs from the repo root with .venv/bin/python
cd "$(dirname "$0")/.." || exit 2
PY=.venv/bin/python
status=0
results=""
for step in server scripts mypy; do
    case $step in
        server)  set -- -m pytest -q ;;
        scripts) set -- -m pytest scripts -q ;;
        mypy)    set -- -m mypy ;;
    esac
    echo "== $step: $PY $*"
    out=$("$PY" "$@" 2>&1)
    code=$?
    printf '%s\n' "$out" | tail -n 15
    last=$(printf '%s\n' "$out" | grep -v '^[[:space:]]*$' | tail -n 1)
    if [ $code -eq 0 ]; then mark=ok; else mark=FAILED; status=1; fi
    results="$results
$step: $mark ($last)"
done
echo "== results:$results"
exit $status

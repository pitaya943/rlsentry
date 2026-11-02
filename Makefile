# Frozen with the harness. The human checks it against the `harness-frozen` tag before approvals.
PY ?= python3
TESTS ?=

.PHONY: harness-test check verify-milestone acceptance status ready render validate

harness-test:            ## Stage 0 step 1: test the harness itself
	$(PY) -m pytest -q harness/tests

REGRESSION ?=

check:                   ## run by `tickets.py accept` after a trial merge
	@if command -v ruff >/dev/null 2>&1; then ruff check .; fi
	@if [ -n "$(TESTS)" ]; then $(PY) -m pytest -q $(TESTS); fi
	@if [ -n "$(REGRESSION)" ]; then $(PY) -m pytest -q $(REGRESSION); fi

verify-milestone:        ## the human's independent check at each gate: make verify-milestone MS=MS3
	@test -n "$(MS)" || (echo "usage: make verify-milestone MS=<milestone>" && exit 2)
	$(PY) harness/acceptance.py --milestone $(MS)

acceptance:              ## final delivery check (MS7)
	$(PY) harness/acceptance.py --final

status:
	$(PY) harness/tickets.py status
ready:
	$(PY) harness/tickets.py ready
render:
	$(PY) harness/tickets.py render
validate:
	$(PY) harness/tickets.py validate

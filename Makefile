PYTHON ?= python
PYTEST ?= $(PYTHON) -m pytest

.PHONY: test unit contract smoke check-endpoints check-endpoints-offline

test: unit contract smoke

unit:
	$(PYTEST)

contract:
	$(PYTEST) \
		tests/unit/test_read_regressions.py \
		tests/unit/test_semantic_tools.py \
		tests/unit/test_write_tools.py

smoke:
	$(PYTEST) tests/unit/test_mcp_smoke.py -k "not live"

check-endpoints:
	$(PYTHON) scripts/check_endpoints.py --skip-sample-capture $(CHECK_ENDPOINTS_ARGS)

check-endpoints-offline:
	$(PYTHON) scripts/check_endpoints.py --skip-endpoint-checks --skip-sample-capture

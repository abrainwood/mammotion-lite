PYTHON := $(shell pyenv which python 2>/dev/null || echo python3)
PYTEST := $(PYTHON) -m pytest

.PHONY: test test-unit test-integration test-e2e dev dev-stop dev-nuke

test:
	$(PYTEST) tests/ -v --tb=short

test-unit:
	$(PYTEST) tests/unit/ -v --tb=short

test-integration:
	$(PYTEST) tests/integration/ -v --tb=short

test-e2e:
	$(PYTEST) tests/e2e/ -v --tb=short -x

dev:
	docker compose -f docker-compose.dev.yml up -d
	@echo "HA running at http://localhost:8123"

dev-stop:
	docker compose -f docker-compose.dev.yml down

dev-nuke:
	@echo "This will DELETE the dev volume (all HA config/state). Are you sure?"
	@read -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ] || exit 1
	docker compose -f docker-compose.dev.yml down
	docker volume rm -f mammotion-lite_ha-mammotion-dev-config

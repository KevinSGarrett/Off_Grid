PYTHON ?= python
WAVE ?= 4
OUTPUT_DIR ?= /mnt/data
PREVIOUS_PACK ?=

.PHONY: test test-private test-monolithic architecture-check schema-check github-check privacy-check migrate api-dev web-dev demo-seed reset-demo wave17-proof pack verify-pack

test:
	$(PYTHON) scripts/run_public_test_matrix.py

test-private:
	$(PYTHON) -m pytest -q

test-monolithic:
	$(PYTHON) -m pytest -q

architecture-check:
	$(PYTHON) -m pytest -q tests/unit/test_wave03_architecture.py tests/unit/test_wave03_state_machines.py tests/unit/test_wave03_write_policy.py


github-check:
	$(PYTHON) scripts/validate_github_config.py

privacy-check:
	$(PYTHON) scripts/validate_git_privacy.py

schema-check:
	$(PYTHON) -m pytest -q tests/unit/test_wave04_models.py tests/unit/test_wave04_privacy.py tests/unit/test_wave04_provenance.py tests/unit/test_wave04_migration.py tests/unit/test_wave04_catalogs.py

migrate:
	PYTHONPATH=apps/api alembic upgrade head

api-dev:
	PYTHONPATH=apps/api uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

web-dev:
	npm --prefix apps/web run dev

pack:
	$(PYTHON) scripts/build_wave_packs.py --wave $(WAVE) --output-dir $(OUTPUT_DIR) $(if $(PREVIOUS_PACK),--previous-pack $(PREVIOUS_PACK),)

verify-pack:
	$(PYTHON) scripts/verify_wave_packs.py $(PACK) $(if $(PREVIOUS_PACK),--previous-pack $(PREVIOUS_PACK),)

aws-check:
	python scripts/validate_aws_infra.py


demo-seed:
	PYTHONPATH=apps/api $(PYTHON) scripts/build_demo_seed.py

reset-demo:
	$(PYTHON) scripts/reset_demo_db.py

wave17-proof:
	PYTHONPATH=apps/api $(PYTHON) scripts/verify_wave17_integration.py

.PHONY: codex-doctor codex-status codex-next wave19-check codex-pack

codex-doctor:
	$(PYTHON) scripts/codex_control.py doctor

codex-status:
	$(PYTHON) scripts/codex_control.py status

codex-next:
	$(PYTHON) scripts/codex_control.py next

wave19-check:
	$(PYTHON) scripts/validate_wave19_codex_pack.py

codex-pack:
	$(PYTHON) scripts/build_codex_standalone_pack.py --output $(OUTPUT_DIR)/OffGrid_Codex_Desktop_Autonomous_Development_W19.zip

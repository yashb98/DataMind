# DataMind — Developer Workflow Makefile
# ============================================================
.PHONY: help up down logs health lint test test-integration build clean

COMPOSE = docker compose
PROFILES = --profile dev

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---- Infrastructure --------------------------------------------------------
up: ## Start all dev services
	$(COMPOSE) $(PROFILES) up -d
	@echo "Waiting for services..."
	@sleep 5
	@$(MAKE) health

up-core: ## Start core services only (no observability)
	$(COMPOSE) --profile core up -d

up-inference: ## Start with local LLM inference (Ollama + vLLM)
	$(COMPOSE) --profile dev --profile inference up -d

up-gdpr: ## Start with Presidio PII services
	$(COMPOSE) --profile dev --profile gdpr up -d

down: ## Stop all services
	$(COMPOSE) down

down-volumes: ## Stop all services AND remove volumes (destructive!)
	$(COMPOSE) down -v

logs: ## Follow logs from all services
	$(COMPOSE) logs -f

logs-%: ## Follow logs for a specific service (e.g. make logs-litellm)
	$(COMPOSE) logs -f $*

health: ## Run health check on all services
	@bash scripts/health-check.sh

health-wait: ## Wait until all services are healthy (max 3 min)
	@bash scripts/health-check.sh --wait --timeout 180

# ---- Development -----------------------------------------------------------
install: ## Install all Python dev dependencies
	pip install uv
	cd apps/api && uv pip install --system -e ".[dev]"
	cd services/slm-router && uv pip install --system -e ".[dev]"
	cd services/auth && uv pip install --system -e ".[dev]"
	cd services/embedding && uv pip install --system -e ".[dev]"

lint: ## Lint all Python code
	ruff check apps/api/src/ services/slm-router/src/ services/auth/src/ services/embedding/src/
	mypy apps/api/src/ services/slm-router/src/ services/auth/src/ --ignore-missing-imports
	bandit -r apps/api/src/ services/slm-router/src/ services/auth/src/ -ll

format: ## Auto-format Python code
	ruff format apps/api/src/ services/slm-router/src/ services/auth/src/ services/embedding/src/

# ---- Testing ---------------------------------------------------------------
test: ## Run all unit tests
	cd apps/api && pytest tests/ -v --cov=src/datamind_api --cov-report=term-missing
	cd services/slm-router && pytest tests/ -v --cov=src/slm_router
	cd services/auth && pytest tests/ -v --cov=src/auth_service

test-api: ## Run FastAPI tests only
	cd apps/api && pytest tests/ -v

test-router: ## Run SLM Router tests only
	cd services/slm-router && pytest tests/ -v

test-auth: ## Run Auth service tests only
	cd services/auth && pytest tests/ -v

test-integration: ## Run integration tests (requires docker compose up)
	DATAMIND_INTEGRATION_TESTS=true pytest tests/integration/ -v -m integration

# ---- Build -----------------------------------------------------------------
build: ## Build all Docker images
	docker build -t datamind-api:dev apps/api/
	docker build -t datamind-auth:dev services/auth/
	docker build -t datamind-slm-router:dev -f services/slm-router/src/slm_router/Dockerfile services/slm-router/
	docker build -t datamind-embedding:dev services/embedding/

# ---- Database --------------------------------------------------------------
db-shell: ## Open PostgreSQL shell
	$(COMPOSE) exec postgres psql -U datamind -d datamind

clickhouse-shell: ## Open ClickHouse client
	$(COMPOSE) exec clickhouse clickhouse-client --password changeme

redis-shell: ## Open Redis CLI
	$(COMPOSE) exec redis redis-cli -a changeme

# ---- Observability UI shortcuts --------------------------------------------
langfuse: ## Open Langfuse in browser
	@echo "Langfuse: http://localhost:3001"
	@open http://localhost:3001 2>/dev/null || xdg-open http://localhost:3001 2>/dev/null || true

grafana: ## Open Grafana in browser
	@echo "Grafana: http://localhost:3002 (admin/changeme)"
	@open http://localhost:3002 2>/dev/null || xdg-open http://localhost:3002 2>/dev/null || true

minio: ## Open MinIO console in browser
	@echo "MinIO: http://localhost:9001 (minioadmin/minioadmin)"
	@open http://localhost:9001 2>/dev/null || xdg-open http://localhost:9001 2>/dev/null || true

# ---- Cleanup ---------------------------------------------------------------
clean: ## Remove build artefacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true

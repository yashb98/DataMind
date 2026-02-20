#!/usr/bin/env bash
# DataMind — Service Health Check Script
# Day 2: Verify all infrastructure services are healthy before proceeding.
# Usage: ./scripts/health-check.sh [--wait] [--timeout 120]

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

WAIT_MODE=false
TIMEOUT=120
START_TIME=$(date +%s)

while [[ $# -gt 0 ]]; do
  case $1 in
    --wait)    WAIT_MODE=true; shift ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

log_ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
log_fail() { echo -e "  ${RED}✗${NC} $1"; }
log_warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
log_info() { echo -e "  ${BLUE}→${NC} $1"; }

check_http() {
  local name="$1" url="$2"
  if curl -sf --max-time 5 "$url" > /dev/null 2>&1; then
    log_ok "$name ($url)"
    return 0
  else
    log_fail "$name ($url) — UNREACHABLE"
    return 1
  fi
}

check_tcp() {
  local name="$1" host="$2" port="$3"
  if nc -z -w 3 "$host" "$port" 2>/dev/null; then
    log_ok "$name ($host:$port)"
    return 0
  else
    log_fail "$name ($host:$port) — UNREACHABLE"
    return 1
  fi
}

run_checks() {
  local failed=0

  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  DataMind Infrastructure Health Check"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""

  echo "📦  Core Databases"
  check_tcp  "PostgreSQL 16"     "localhost" "5432"       || ((failed++))
  check_http "ClickHouse HTTP"   "http://localhost:8123/ping" || ((failed++))
  check_http "Qdrant"            "http://localhost:6333/health" || ((failed++))
  check_tcp  "Redis"             "localhost" "6379"       || ((failed++))
  check_tcp  "MongoDB"           "localhost" "27017"      || ((failed++))
  check_http "Neo4j Browser"     "http://localhost:7474"  || ((failed++))

  echo ""
  echo "🗄️   Object Storage & Lakehouse"
  check_http "MinIO S3 API"      "http://localhost:9000/minio/health/live" || ((failed++))
  check_http "MinIO Console"     "http://localhost:9001"  || ((failed++))
  check_http "Nessie Catalog"    "http://localhost:19120/api/v1/config" || ((failed++))

  echo ""
  echo "📨  Message Streaming"
  check_tcp  "Kafka Broker"      "localhost" "9092"       || ((failed++))
  check_http "Schema Registry"   "http://localhost:8081/subjects" || ((failed++))

  echo ""
  echo "🤖  AI & Inference"
  check_http "LiteLLM Proxy"     "http://localhost:4000/health/liveliness" || ((failed++))
  check_http "Ollama"            "http://localhost:11434/api/tags" || ((failed++))
  check_http "SLM Router"        "http://localhost:8020/health/liveness" || ((failed++)) || log_warn "SLM Router not yet deployed (Day 2)"
  check_http "Embedding Service" "http://localhost:8030/health/liveness" || ((failed++)) || log_warn "Embedding service not yet deployed (Day 2)"

  echo ""
  echo "🔍  Observability"
  check_http "Langfuse"          "http://localhost:3001/api/public/health" || ((failed++))
  check_http "Grafana"           "http://localhost:3002" || ((failed++))
  check_http "Prometheus"        "http://localhost:9090/-/healthy" || ((failed++))
  check_http "Jaeger UI"         "http://localhost:16686" || ((failed++))
  check_http "OTel Collector"    "http://localhost:55679" || ((failed++)) || log_warn "OTel zpages may not be enabled"

  echo ""
  echo "🔒  Privacy (GDPR)"
  check_http "Presidio Analyzer"   "http://localhost:5001/health" || log_warn "Presidio not running (use --profile gdpr)"
  check_http "Presidio Anonymizer" "http://localhost:5002/health" || log_warn "Presidio not running (use --profile gdpr)"

  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  if [[ $failed -eq 0 ]]; then
    echo -e "  ${GREEN}All services healthy ✓${NC}"
  else
    echo -e "  ${RED}$failed service(s) unhealthy ✗${NC}"
  fi
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""

  return $failed
}

if $WAIT_MODE; then
  log_info "Waiting for all services (timeout: ${TIMEOUT}s)..."
  while true; do
    ELAPSED=$(( $(date +%s) - START_TIME ))
    if [[ $ELAPSED -gt $TIMEOUT ]]; then
      echo -e "${RED}Timeout after ${TIMEOUT}s — services not ready${NC}"
      exit 1
    fi
    if run_checks 2>/dev/null; then
      echo -e "${GREEN}All services ready after ${ELAPSED}s${NC}"
      exit 0
    fi
    echo -e "${YELLOW}Not ready yet (${ELAPSED}s elapsed), retrying in 10s...${NC}"
    sleep 10
  done
else
  run_checks
  exit $?
fi

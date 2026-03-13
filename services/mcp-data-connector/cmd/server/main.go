// Package main — Entry point for the mcp-data-connector service.
// Day 11: MCP data connector service — HTTP server wiring, Prometheus metrics, graceful shutdown.
//
// Protocols: MCP JSON-RPC 2.0 (streamable-HTTP transport on POST /mcp/)
// SOLID: DIP (all components constructed here and injected), SRP (wiring only)
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.uber.org/zap"

	"github.com/yashb98/datamind/mcp-data-connector/internal/config"
	"github.com/yashb98/datamind/mcp-data-connector/internal/connector"
	"github.com/yashb98/datamind/mcp-data-connector/internal/ingestion"
	mcpserver "github.com/yashb98/datamind/mcp-data-connector/internal/mcp"
	"github.com/yashb98/datamind/mcp-data-connector/internal/models"
	"github.com/yashb98/datamind/mcp-data-connector/internal/profiler"
)

// ─── Prometheus metrics ───────────────────────────────────────────────────────

var (
	toolCallsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "mcp_dc_tool_calls_total",
			Help: "Total MCP data-connector tool invocations by tool name and status.",
		},
		[]string{"tool", "status"},
	)
	toolLatencyMs = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "mcp_dc_tool_latency_ms",
			Help:    "MCP data-connector tool call latency in milliseconds.",
			Buckets: []float64{10, 50, 100, 500, 1000, 5000, 15000, 30000, 60000},
		},
		[]string{"tool"},
	)
	activeConnections = prometheus.NewGauge(prometheus.GaugeOpts{
		Name: "mcp_dc_active_connections",
		Help: "Number of currently registered data source connections.",
	})
)

func main() {
	cfg := config.Load()

	// Production-grade structured logger
	logger, err := zap.NewProduction()
	if err != nil {
		panic(fmt.Sprintf("failed to initialise logger: %v", err))
	}
	defer logger.Sync() //nolint:errcheck

	// Register Prometheus metrics
	prometheus.MustRegister(toolCallsTotal, toolLatencyMs, activeConnections)

	// ── Build dependency graph (composition root) ─────────────────────────────

	registry := connector.NewConnectorRegistry()

	// IcebergWriter: best-effort — MinIO may not be reachable in all environments
	writer, err := ingestion.NewIcebergWriter(
		cfg.MinIOEndpoint,
		cfg.MinIOAccessKey,
		cfg.MinIOSecretKey,
		cfg.MinIOBucket,
		cfg.MinIOSecure,
	)
	if err != nil {
		logger.Warn("minio.client.init.failed",
			zap.Error(err),
			zap.String("endpoint", cfg.MinIOEndpoint),
			zap.String("hint", "ingest tool will return error until MinIO is reachable"),
		)
	}

	// pipeline is nil when MinIO is unavailable; handled gracefully in the MCP server
	var pipeline *ingestion.IngestionPipeline
	if writer != nil {
		pipeline = ingestion.NewIngestionPipeline(writer)
	}

	schemaProfiler := &profiler.SchemaProfiler{}
	mcpSrv := mcpserver.NewServer(registry, pipeline, schemaProfiler, logger)

	// ── HTTP router ────────────────────────────────────────────────────────────

	mux := http.NewServeMux()

	// Kubernetes liveness probe
	mux.HandleFunc("/health/liveness", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{ //nolint:errcheck
			"status":  "alive",
			"service": cfg.ServiceName,
		})
	})

	// Kubernetes readiness probe
	mux.HandleFunc("/health/readiness", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{ //nolint:errcheck
			"status":  "healthy",
			"service": cfg.ServiceName,
		})
	})

	// Tool discovery endpoint (non-MCP convenience route for service mesh)
	mux.HandleFunc("/tools", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{ //nolint:errcheck
			"tools":        []string{"connect", "ingest", "profile_schema"},
			"mcp_endpoint": "/mcp/",
			"transport":    "streamable-http",
			"service":      cfg.ServiceName,
			"version":      "1.0.0",
		})
	})

	// MCP JSON-RPC 2.0 endpoint (streamable-HTTP transport)
	mux.HandleFunc("/mcp/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed; MCP requires POST", http.StatusMethodNotAllowed)
			return
		}

		body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20)) // 1 MiB request limit
		if err != nil {
			http.Error(w, "failed to read request body", http.StatusBadRequest)
			return
		}

		var req models.JSONRPCRequest
		if err := json.Unmarshal(body, &req); err != nil {
			http.Error(w, fmt.Sprintf("invalid JSON: %s", err.Error()), http.StatusBadRequest)
			return
		}

		// Dispatch and measure latency
		callStart := time.Now()
		resp := mcpSrv.Handle(r.Context(), req)
		elapsedMs := float64(time.Since(callStart).Microseconds()) / 1000.0

		// Derive tool name for metric labels
		toolName := deriveToolName(req)
		toolLatencyMs.WithLabelValues(toolName).Observe(elapsedMs)
		status := "ok"
		if resp.Error != nil {
			status = "error"
		}
		toolCallsTotal.WithLabelValues(toolName, status).Inc()
		activeConnections.Set(float64(registry.Len()))

		w.Header().Set("Content-Type", "application/json")
		if err := json.NewEncoder(w).Encode(resp); err != nil {
			logger.Error("http.encode.response.failed", zap.Error(err))
		}
	})

	// Prometheus metrics scrape endpoint
	mux.Handle("/metrics", promhttp.Handler())

	// ── HTTP server lifecycle ─────────────────────────────────────────────────

	httpServer := &http.Server{
		Addr:         fmt.Sprintf(":%d", cfg.Port),
		Handler:      mux,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 300 * time.Second, // allow long ingest operations
		IdleTimeout:  120 * time.Second,
	}

	go func() {
		logger.Info("server.starting",
			zap.String("service", cfg.ServiceName),
			zap.Int("port", cfg.Port),
			zap.String("mcp_endpoint", "/mcp/"),
		)
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Fatal("server.failed", zap.Error(err))
		}
	}()

	// Wait for OS termination signal
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	sig := <-quit
	logger.Info("server.shutdown.initiated", zap.String("signal", sig.String()))

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	if err := httpServer.Shutdown(ctx); err != nil {
		logger.Error("server.shutdown.error", zap.Error(err))
	}
	logger.Info("server.stopped")
}

// deriveToolName extracts the tool name from a tools/call request for use in metric labels.
// Returns "tools_list" for tools/list, the tool name for tools/call, and "unknown" otherwise.
func deriveToolName(req models.JSONRPCRequest) string {
	if req.Method == "tools/list" {
		return "tools_list"
	}
	if req.Method == "tools/call" {
		if params, ok := req.Params.(map[string]interface{}); ok {
			if name, ok := params["name"].(string); ok && name != "" {
				return name
			}
		}
	}
	return "unknown"
}

// Package mcp — MCP JSON-RPC 2.0 server for the data connector service.
// Day 11: MCP data connector service — protocol handler for tools/list and tools/call.
//
// Protocols: MCP JSON-RPC 2.0 (streamable-HTTP transport)
// SOLID: SRP (protocol handling only — no business logic), DIP (injected dependencies)
package mcp

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"go.uber.org/zap"

	"github.com/yashb98/datamind/mcp-data-connector/internal/connector"
	"github.com/yashb98/datamind/mcp-data-connector/internal/ingestion"
	"github.com/yashb98/datamind/mcp-data-connector/internal/models"
	"github.com/yashb98/datamind/mcp-data-connector/internal/profiler"
)

// Server handles MCP JSON-RPC 2.0 requests.
//
// SOLID SRP: protocol dispatch only — business logic lives in pipeline/profiler/registry.
// SOLID DIP: all collaborators are injected at construction time.
type Server struct {
	registry *connector.ConnectorRegistry
	pipeline *ingestion.IngestionPipeline // may be nil when MinIO is unavailable
	profiler *profiler.SchemaProfiler
	logger   *zap.Logger
}

// NewServer creates an MCP server with the given collaborators.
// pipeline may be nil; the ingest handler will return a descriptive error in that case.
func NewServer(
	registry *connector.ConnectorRegistry,
	pipeline *ingestion.IngestionPipeline,
	schemaProfiler *profiler.SchemaProfiler,
	logger *zap.Logger,
) *Server {
	return &Server{
		registry: registry,
		pipeline: pipeline,
		profiler: schemaProfiler,
		logger:   logger,
	}
}

// Handle dispatches an MCP JSON-RPC 2.0 request to the appropriate handler.
// All responses carry JSONRPC:"2.0" and the original request ID.
func (s *Server) Handle(ctx context.Context, req models.JSONRPCRequest) models.JSONRPCResponse {
	switch req.Method {
	case "tools/list":
		return s.handleToolsList(req)
	case "tools/call":
		return s.handleToolsCall(ctx, req)
	default:
		return errorResponse(req.ID, -32601,
			fmt.Sprintf("method not found: %q; supported: tools/list, tools/call", req.Method))
	}
}

// ─── tools/list ──────────────────────────────────────────────────────────────

func (s *Server) handleToolsList(req models.JSONRPCRequest) models.JSONRPCResponse {
	tools := models.ToolsListResult{
		Tools: []models.ToolDefinition{
			{
				Name:        "connect",
				Description: "Test and register a data source connection. Supported source types: postgres, mysql, s3, kafka, csv, bigquery, snowflake.",
				InputSchema: map[string]interface{}{
					"type": "object",
					"properties": map[string]interface{}{
						"source_type": map[string]interface{}{
							"type":        "string",
							"description": "Type of data source: postgres | mysql | s3 | kafka | csv | bigquery | snowflake",
							"enum":        []string{"postgres", "mysql", "s3", "kafka", "csv", "bigquery", "snowflake"},
						},
						"connection_config": map[string]interface{}{
							"type":        "object",
							"description": "Provider-specific connection parameters (host, port, user, password, etc.)",
						},
						"tenant_id": map[string]interface{}{
							"type":        "string",
							"description": "Tenant identifier for multi-tenancy isolation",
						},
						"source_name": map[string]interface{}{
							"type":        "string",
							"description": "Human-readable name for this connection (used in connection_id)",
						},
					},
					"required": []string{"source_type", "connection_config", "tenant_id", "source_name"},
				},
			},
			{
				Name:        "ingest",
				Description: "Pull data from a registered connection into MinIO/Iceberg via the Nessie REST catalog. Returns job_id, rows_ingested, bytes_written, and iceberg_path.",
				InputSchema: map[string]interface{}{
					"type": "object",
					"properties": map[string]interface{}{
						"connection_id": map[string]interface{}{
							"type":        "string",
							"description": "connection_id returned by the connect tool",
						},
						"tenant_id": map[string]interface{}{
							"type":        "string",
							"description": "Tenant identifier; used to namespace the Iceberg path",
						},
						"table_name": map[string]interface{}{
							"type":        "string",
							"description": "Source table name (or Kafka topic for kafka sources)",
						},
						"query": map[string]interface{}{
							"type":        "string",
							"description": "Optional SQL query; defaults to SELECT * FROM table_name",
						},
						"batch_size": map[string]interface{}{
							"type":        "integer",
							"description": "Maximum number of rows to ingest in one job (default 1000)",
						},
						"destination_path": map[string]interface{}{
							"type":        "string",
							"description": "Optional MinIO object path; auto-generated if omitted",
						},
					},
					"required": []string{"connection_id", "tenant_id", "table_name"},
				},
			},
			{
				Name:        "profile_schema",
				Description: "Profile a source table: row count, per-column null %, cardinality, and PII detection (email, phone, SSN, credit card, name, address, IP, DOB, etc.).",
				InputSchema: map[string]interface{}{
					"type": "object",
					"properties": map[string]interface{}{
						"connection_id": map[string]interface{}{
							"type":        "string",
							"description": "connection_id returned by the connect tool",
						},
						"tenant_id": map[string]interface{}{
							"type":        "string",
							"description": "Tenant identifier (used for audit logging)",
						},
						"table_name": map[string]interface{}{
							"type":        "string",
							"description": "Table to profile",
						},
						"sample_rows": map[string]interface{}{
							"type":        "integer",
							"description": "Number of rows to sample for statistics (default 1000)",
						},
					},
					"required": []string{"connection_id", "tenant_id", "table_name"},
				},
			},
		},
	}
	return models.JSONRPCResponse{JSONRPC: "2.0", Result: tools, ID: req.ID}
}

// ─── tools/call dispatcher ───────────────────────────────────────────────────

func (s *Server) handleToolsCall(ctx context.Context, req models.JSONRPCRequest) models.JSONRPCResponse {
	paramsBytes, err := json.Marshal(req.Params)
	if err != nil {
		return errorResponse(req.ID, -32600, "invalid params: cannot re-marshal")
	}
	var params models.ToolCallParams
	if err := json.Unmarshal(paramsBytes, &params); err != nil {
		return errorResponse(req.ID, -32600, fmt.Sprintf("invalid params: %s", err.Error()))
	}

	var result interface{}
	switch params.Name {
	case "connect":
		result = s.handleConnect(ctx, params.Arguments)
	case "ingest":
		result = s.handleIngest(ctx, params.Arguments)
	case "profile_schema":
		result = s.handleProfileSchema(ctx, params.Arguments)
	default:
		return errorResponse(req.ID, -32601,
			fmt.Sprintf("unknown tool %q; available: connect, ingest, profile_schema", params.Name))
	}

	resultJSON, _ := json.Marshal(result)
	return models.JSONRPCResponse{
		JSONRPC: "2.0",
		Result: models.ToolCallResult{
			Content: []models.TextContent{{Type: "text", Text: string(resultJSON)}},
		},
		ID: req.ID,
	}
}

// ─── tool handlers ────────────────────────────────────────────────────────────

func (s *Server) handleConnect(ctx context.Context, args map[string]interface{}) interface{} {
	sourceType, _ := args["source_type"].(string)
	config, _ := args["connection_config"].(map[string]interface{})
	tenantID, _ := args["tenant_id"].(string)
	sourceName, _ := args["source_name"].(string)

	if sourceType == "" {
		return models.ConnectResponse{Status: "failed", Error: "source_type is required"}
	}
	if tenantID == "" {
		return models.ConnectResponse{Status: "failed", Error: "tenant_id is required"}
	}
	if sourceName == "" {
		return models.ConnectResponse{Status: "failed", Error: "source_name is required"}
	}

	conn, err := connector.NewConnector(sourceType)
	if err != nil {
		return models.ConnectResponse{Status: "failed", Error: err.Error()}
	}

	start := time.Now()
	schemaCount, err := conn.Connect(ctx, config)
	latencyMs := float64(time.Since(start).Microseconds()) / 1000.0

	if err != nil {
		return models.ConnectResponse{
			Status:    "failed",
			LatencyMs: latencyMs,
			Error:     err.Error(),
		}
	}

	// connection_id format: {tenantID}_{sourceName}_{nanosecond_suffix}
	connID := fmt.Sprintf("%s_%s_%d", tenantID, sourceName, time.Now().UnixNano()%1_000_000)
	s.registry.Register(connID, conn)

	s.logger.Info("connector.registered",
		zap.String("connection_id", connID),
		zap.String("source_type", sourceType),
		zap.String("tenant_id", tenantID),
		zap.Int("schema_count", schemaCount),
		zap.Float64("latency_ms", latencyMs),
	)

	return models.ConnectResponse{
		ConnectionID: connID,
		Status:       "connected",
		LatencyMs:    latencyMs,
		SchemaCount:  schemaCount,
	}
}

func (s *Server) handleIngest(ctx context.Context, args map[string]interface{}) interface{} {
	connID, _ := args["connection_id"].(string)
	tenantID, _ := args["tenant_id"].(string)
	tableName, _ := args["table_name"].(string)
	query, _ := args["query"].(string)
	destinationPath, _ := args["destination_path"].(string)

	batchSize := 1000
	if bs, ok := args["batch_size"].(float64); ok && bs > 0 {
		batchSize = int(bs)
	}

	if connID == "" {
		return models.IngestResponse{Status: "error", Error: "connection_id is required"}
	}
	if tableName == "" {
		return models.IngestResponse{Status: "error", Error: "table_name is required"}
	}

	if s.pipeline == nil {
		return models.IngestResponse{
			Status: "error",
			Error:  "ingestion pipeline unavailable; check MINIO_ENDPOINT and MINIO_ACCESS_KEY configuration",
		}
	}

	conn, err := s.registry.Get(connID)
	if err != nil {
		return models.IngestResponse{Status: "error", Error: err.Error()}
	}

	req := models.IngestRequest{
		ConnectionID:    connID,
		TenantID:        tenantID,
		TableName:       tableName,
		Query:           query,
		BatchSize:       batchSize,
		DestinationPath: destinationPath,
	}

	resp, _ := s.pipeline.Ingest(ctx, conn, req)

	s.logger.Info("ingest.completed",
		zap.String("job_id", resp.JobID),
		zap.String("connection_id", connID),
		zap.String("table", tableName),
		zap.Int64("rows", resp.RowsIngested),
		zap.String("status", resp.Status),
	)

	return resp
}

func (s *Server) handleProfileSchema(ctx context.Context, args map[string]interface{}) interface{} {
	connID, _ := args["connection_id"].(string)
	tenantID, _ := args["tenant_id"].(string)
	tableName, _ := args["table_name"].(string)

	sampleRows := 1000
	if sr, ok := args["sample_rows"].(float64); ok && sr > 0 {
		sampleRows = int(sr)
	}

	if connID == "" {
		return map[string]string{"error": "connection_id is required", "code": "MISSING_PARAM"}
	}
	if tableName == "" {
		return map[string]string{"error": "table_name is required", "code": "MISSING_PARAM"}
	}

	conn, err := s.registry.Get(connID)
	if err != nil {
		return map[string]string{"error": err.Error(), "code": "CONNECTION_NOT_FOUND"}
	}

	_ = tenantID // reserved for audit logging / row-level security checks

	resp, err := s.profiler.Profile(ctx, conn, tableName, sampleRows)
	if err != nil {
		return map[string]string{"error": err.Error(), "code": "PROFILE_FAILED"}
	}

	s.logger.Info("profile.completed",
		zap.String("connection_id", connID),
		zap.String("table", tableName),
		zap.Int("columns", len(resp.Columns)),
		zap.Int64("row_count", resp.RowCount),
	)

	return resp
}

// ─── helpers ──────────────────────────────────────────────────────────────────

func errorResponse(id interface{}, code int, msg string) models.JSONRPCResponse {
	return models.JSONRPCResponse{
		JSONRPC: "2.0",
		Error:   &models.RPCError{Code: code, Message: msg},
		ID:      id,
	}
}

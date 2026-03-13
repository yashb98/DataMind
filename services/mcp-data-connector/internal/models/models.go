// Package models — Request/response structs for mcp-data-connector.
// Day 11: MCP data connector service — Pydantic-equivalent Go structs.
//
// Protocols: MCP JSON-RPC 2.0
// SOLID: SRP (data shapes only, no business logic)
package models

import "time"

// ─── MCP JSON-RPC 2.0 envelope types ────────────────────────────────────────

// JSONRPCRequest is the MCP JSON-RPC 2.0 request envelope.
type JSONRPCRequest struct {
	JSONRPC string      `json:"jsonrpc"`
	Method  string      `json:"method"`
	Params  interface{} `json:"params"`
	ID      interface{} `json:"id"`
}

// JSONRPCResponse is the MCP JSON-RPC 2.0 response envelope.
type JSONRPCResponse struct {
	JSONRPC string      `json:"jsonrpc"`
	Result  interface{} `json:"result,omitempty"`
	Error   *RPCError   `json:"error,omitempty"`
	ID      interface{} `json:"id"`
}

// RPCError represents a JSON-RPC 2.0 error object.
type RPCError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

// ToolsListResult is the response body for tools/list.
type ToolsListResult struct {
	Tools []ToolDefinition `json:"tools"`
}

// ToolDefinition describes a single MCP tool in the tools/list response.
type ToolDefinition struct {
	Name        string      `json:"name"`
	Description string      `json:"description"`
	InputSchema interface{} `json:"inputSchema"`
}

// ToolCallParams is the params object for a tools/call request.
type ToolCallParams struct {
	Name      string                 `json:"name"`
	Arguments map[string]interface{} `json:"arguments"`
}

// ToolCallResult wraps a tool's output as MCP content blocks.
type ToolCallResult struct {
	Content []TextContent `json:"content"`
}

// TextContent is an MCP text content block (type="text").
type TextContent struct {
	Type string `json:"type"`
	Text string `json:"text"`
}

// ─── connect tool ────────────────────────────────────────────────────────────

// ConnectRequest is the input schema for the `connect` tool.
type ConnectRequest struct {
	SourceType       string                 `json:"source_type"`
	ConnectionConfig map[string]interface{} `json:"connection_config"`
	TenantID         string                 `json:"tenant_id"`
	SourceName       string                 `json:"source_name"`
}

// ConnectResponse is the output of the `connect` tool.
type ConnectResponse struct {
	ConnectionID string  `json:"connection_id"`
	Status       string  `json:"status"`
	LatencyMs    float64 `json:"latency_ms"`
	SchemaCount  int     `json:"schema_count"`
	Error        string  `json:"error,omitempty"`
}

// ─── ingest tool ─────────────────────────────────────────────────────────────

// IngestRequest is the input schema for the `ingest` tool.
type IngestRequest struct {
	ConnectionID    string `json:"connection_id"`
	TenantID        string `json:"tenant_id"`
	TableName       string `json:"table_name"`
	Query           string `json:"query,omitempty"`
	BatchSize       int    `json:"batch_size"`
	DestinationPath string `json:"destination_path,omitempty"`
}

// IngestResponse is the output of the `ingest` tool.
type IngestResponse struct {
	JobID        string  `json:"job_id"`
	RowsIngested int64   `json:"rows_ingested"`
	BytesWritten int64   `json:"bytes_written"`
	IcebergPath  string  `json:"iceberg_path"`
	DurationMs   float64 `json:"duration_ms"`
	Status       string  `json:"status"`
	Error        string  `json:"error,omitempty"`
}

// ─── profile_schema tool ──────────────────────────────────────────────────────

// ProfileRequest is the input schema for the `profile_schema` tool.
type ProfileRequest struct {
	ConnectionID string `json:"connection_id"`
	TenantID     string `json:"tenant_id"`
	TableName    string `json:"table_name"`
	SampleRows   int    `json:"sample_rows"`
}

// ColumnProfile holds statistics and PII information for one column.
type ColumnProfile struct {
	Name        string  `json:"name"`
	Type        string  `json:"type"`
	NullPct     float64 `json:"null_pct"`
	Cardinality int64   `json:"cardinality"`
	PIIDetected bool    `json:"pii_detected"`
	PIIType     string  `json:"pii_type,omitempty"`
}

// ProfileResponse is the output of the `profile_schema` tool.
type ProfileResponse struct {
	TableName  string          `json:"table_name"`
	RowCount   int64           `json:"row_count"`
	Columns    []ColumnProfile `json:"columns"`
	ProfiledAt time.Time       `json:"profiled_at"`
}

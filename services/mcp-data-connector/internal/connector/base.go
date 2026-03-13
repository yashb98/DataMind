// Package connector — IConnector interface and shared utilities for data source connectors.
// Day 11: MCP data connector service — SOLID OCP-compliant connector abstraction.
//
// Protocols: MCP
// SOLID: OCP (new connectors = new file implementing IConnector), ISP (lean interface)
package connector

import "context"

// IConnector is the base interface for all data source connectors.
//
// SOLID OCP: Adding support for a new data source means creating a new file
// that implements this interface — zero modifications to existing code.
// SOLID ISP: Interface is intentionally small (5 methods), avoiding fat interfaces.
type IConnector interface {
	// Connect tests connectivity to the data source and returns the number of schemas/databases found.
	// config is the provider-specific connection map from the MCP call arguments.
	Connect(ctx context.Context, config map[string]interface{}) (int, error)

	// QueryRows executes a SQL query (or equivalent) and returns at most limit rows.
	// For streaming sources (Kafka) this reads up to limit messages.
	QueryRows(ctx context.Context, query string, limit int) ([]map[string]interface{}, error)

	// GetRowCount returns the total number of rows in tableName.
	// Returns -1 if the count is unavailable (e.g. streaming sources).
	GetRowCount(ctx context.Context, tableName string) (int64, error)

	// GetColumns returns the ordered list of columns with their data types.
	GetColumns(ctx context.Context, tableName string) ([]ColumnInfo, error)

	// Close releases all resources held by the connector (connections, file handles, etc.).
	Close() error

	// SourceType returns the canonical source type string (e.g. "postgres", "kafka").
	SourceType() string
}

// ColumnInfo holds the name and database-level type for a single column.
type ColumnInfo struct {
	Name     string
	DataType string
}

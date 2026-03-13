// Package connector — Snowflake connector stub.
// Day 11: MCP data connector service — snowflake IConnector (stub, requires Snowflake account).
//
// Protocols: MCP
// SOLID: OCP (implements IConnector without modifying base.go)
//
// NOTE: Full implementation requires the github.com/snowflakedb/gosnowflake SDK
// and a Snowflake account with account identifier, warehouse, and credentials.
// This stub returns a clear error directing the operator to provide them.
package connector

import (
	"context"
	"fmt"
)

// SnowflakeConnector is a stub IConnector for Snowflake Data Cloud.
// It returns a descriptive error until Snowflake credentials are configured.
type SnowflakeConnector struct{}

// SourceType returns "snowflake".
func (c *SnowflakeConnector) SourceType() string { return "snowflake" }

// Connect always returns an error directing the operator to configure Snowflake credentials.
func (c *SnowflakeConnector) Connect(_ context.Context, _ map[string]interface{}) (int, error) {
	return 0, fmt.Errorf(
		"Snowflake connector requires a Snowflake account and credentials: " +
			"provide account, user, password, warehouse, database, schema in connection_config. " +
			"The github.com/snowflakedb/gosnowflake SDK is not included in the dev build",
	)
}

// QueryRows returns not-connected error.
func (c *SnowflakeConnector) QueryRows(_ context.Context, _ string, _ int) ([]map[string]interface{}, error) {
	return nil, fmt.Errorf("Snowflake connector not configured; call connect tool first with valid Snowflake credentials")
}

// GetRowCount returns not-connected error.
func (c *SnowflakeConnector) GetRowCount(_ context.Context, _ string) (int64, error) {
	return 0, fmt.Errorf("Snowflake connector not configured")
}

// GetColumns returns not-connected error.
func (c *SnowflakeConnector) GetColumns(_ context.Context, _ string) ([]ColumnInfo, error) {
	return nil, fmt.Errorf("Snowflake connector not configured")
}

// Close is a no-op.
func (c *SnowflakeConnector) Close() error { return nil }

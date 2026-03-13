// Package connector — BigQuery connector stub.
// Day 11: MCP data connector service — bigquery IConnector (stub, requires GCP credentials).
//
// Protocols: MCP
// SOLID: OCP (implements IConnector without modifying base.go)
//
// NOTE: Full implementation requires the cloud.google.com/go/bigquery SDK and
// GOOGLE_APPLICATION_CREDENTIALS set in the environment.
// This stub returns a clear error directing the operator to provide credentials.
package connector

import (
	"context"
	"fmt"
)

// BigQueryConnector is a stub IConnector for Google BigQuery.
// It returns a descriptive error until GCP credentials are configured.
type BigQueryConnector struct{}

// SourceType returns "bigquery".
func (c *BigQueryConnector) SourceType() string { return "bigquery" }

// Connect always returns an error directing the operator to set GCP credentials.
func (c *BigQueryConnector) Connect(_ context.Context, _ map[string]interface{}) (int, error) {
	return 0, fmt.Errorf(
		"BigQuery connector requires Google Cloud credentials: " +
			"set GOOGLE_APPLICATION_CREDENTIALS to a service account key file, " +
			"or use Application Default Credentials (gcloud auth application-default login). " +
			"The cloud.google.com/go/bigquery SDK is not included in the dev build",
	)
}

// QueryRows returns not-connected error.
func (c *BigQueryConnector) QueryRows(_ context.Context, _ string, _ int) ([]map[string]interface{}, error) {
	return nil, fmt.Errorf("BigQuery connector not configured; call connect tool first with valid GCP credentials")
}

// GetRowCount returns not-connected error.
func (c *BigQueryConnector) GetRowCount(_ context.Context, _ string) (int64, error) {
	return 0, fmt.Errorf("BigQuery connector not configured")
}

// GetColumns returns not-connected error.
func (c *BigQueryConnector) GetColumns(_ context.Context, _ string) ([]ColumnInfo, error) {
	return nil, fmt.Errorf("BigQuery connector not configured")
}

// Close is a no-op.
func (c *BigQueryConnector) Close() error { return nil }

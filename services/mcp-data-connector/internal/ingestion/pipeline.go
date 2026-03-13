// Package ingestion — IngestionPipeline: orchestrates data extraction and Iceberg loading.
// Day 11: MCP data connector service — ingest tool backend.
//
// Protocols: MCP
// SOLID: SRP (orchestration only), DIP (depends on IConnector + IcebergWriter ABCs)
// Benchmark: tests/benchmarks/bench_ingest.go
package ingestion

import (
	"context"
	"fmt"
	"time"

	"github.com/yashb98/datamind/mcp-data-connector/internal/connector"
	"github.com/yashb98/datamind/mcp-data-connector/internal/models"
)

// IngestionPipeline coordinates data extraction from a source connector
// and loading into the MinIO/Iceberg sink.
//
// SOLID DIP: depends on connector.IConnector and IcebergWriter interfaces.
type IngestionPipeline struct {
	writer *IcebergWriter
}

// NewIngestionPipeline creates a pipeline backed by writer.
// writer may be nil (MinIO unavailable); Ingest will return an error in that case.
func NewIngestionPipeline(writer *IcebergWriter) *IngestionPipeline {
	return &IngestionPipeline{writer: writer}
}

// Ingest extracts rows from conn using the parameters in req, serialises them
// as NDJSON, and writes the result to MinIO/Iceberg.
//
// Args:
//
//	ctx  - context honouring cancellation / deadline
//	conn - active IConnector (already Connected)
//	req  - ingest parameters (table, optional query, batch size, destination path)
//
// Returns a non-nil IngestResponse for all outcomes, with Status="error" and Error set on failure.
func (p *IngestionPipeline) Ingest(
	ctx context.Context,
	conn connector.IConnector,
	req models.IngestRequest,
) (*models.IngestResponse, error) {
	start := time.Now()
	jobID := generateJobID()

	if p.writer == nil {
		return &models.IngestResponse{
			JobID:      jobID,
			Status:     "error",
			DurationMs: float64(time.Since(start).Milliseconds()),
			Error:      "MinIO/Iceberg writer unavailable; check MINIO_ENDPOINT configuration",
		}, nil
	}

	// Build the extraction query
	query := req.Query
	if query == "" {
		query = fmt.Sprintf("SELECT * FROM %s", req.TableName) //nolint:gosec
	}
	if req.BatchSize <= 0 {
		req.BatchSize = 1000
	}

	// Extract rows from the source
	rows, err := conn.QueryRows(ctx, query, req.BatchSize)
	if err != nil {
		return &models.IngestResponse{
			JobID:      jobID,
			Status:     "error",
			DurationMs: float64(time.Since(start).Milliseconds()),
			Error:      fmt.Sprintf("extract rows: %s", err.Error()),
		}, nil
	}

	// Determine the MinIO object path
	objectPath := req.DestinationPath
	if objectPath == "" {
		objectPath = fmt.Sprintf(
			"%s/raw/%s/%s_%s.ndjson",
			req.TenantID, req.TableName, req.TableName, jobID,
		)
	}

	// Write to MinIO/Iceberg
	bytesWritten, err := p.writer.WriteNDJSON(ctx, objectPath, rows)
	duration := time.Since(start)

	if err != nil {
		return &models.IngestResponse{
			JobID:      jobID,
			Status:     "error",
			DurationMs: float64(duration.Milliseconds()),
			Error:      fmt.Sprintf("write iceberg: %s", err.Error()),
		}, nil
	}

	return &models.IngestResponse{
		JobID:        jobID,
		RowsIngested: int64(len(rows)),
		BytesWritten: bytesWritten,
		IcebergPath:  objectPath,
		DurationMs:   float64(duration.Milliseconds()),
		Status:       "success",
	}, nil
}

// generateJobID creates a short unique job identifier using the current Unix nanosecond.
// Collisions are extremely unlikely within a single service instance.
func generateJobID() string {
	return fmt.Sprintf("job_%d", time.Now().UnixNano()%1_000_000_000)
}

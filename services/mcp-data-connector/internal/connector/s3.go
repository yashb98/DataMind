// Package connector — S3/MinIO connector implementation.
// Day 11: MCP data connector service — s3/minio IConnector.
//
// Protocols: MCP
// SOLID: OCP (implements IConnector without modifying base.go), SRP (object storage only)
package connector

import (
	"context"
	"fmt"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

// S3Connector implements IConnector for S3-compatible object stores (AWS S3, MinIO, GCS).
// Since object stores are schema-less, SQL queries are not supported; use the ingest
// tool to move files into Iceberg for structured querying.
type S3Connector struct {
	client *minio.Client
	bucket string
}

// SourceType returns "s3".
func (c *S3Connector) SourceType() string { return "s3" }

// Connect verifies that the bucket exists and is accessible.
//
// Required config keys: endpoint, access_key, secret_key, bucket.
// Optional: use_ssl (default false).
func (c *S3Connector) Connect(ctx context.Context, config map[string]interface{}) (int, error) {
	endpoint, _ := config["endpoint"].(string)
	accessKey, _ := config["access_key"].(string)
	secretKey, _ := config["secret_key"].(string)
	bucket, _ := config["bucket"].(string)
	useSSL, _ := config["use_ssl"].(bool)

	if endpoint == "" {
		return 0, fmt.Errorf("endpoint required for S3/MinIO connector")
	}
	if bucket == "" {
		return 0, fmt.Errorf("bucket required for S3/MinIO connector")
	}

	client, err := minio.New(endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(accessKey, secretKey, ""),
		Secure: useSSL,
	})
	if err != nil {
		return 0, fmt.Errorf("create minio client: %w", err)
	}

	// Test connectivity: bucket existence check
	exists, err := client.BucketExists(ctx, bucket)
	if err != nil {
		return 0, fmt.Errorf("check bucket existence: %w", err)
	}
	if !exists {
		return 0, fmt.Errorf("bucket %q not found or not accessible", bucket)
	}

	c.client = client
	c.bucket = bucket
	return 1, nil // 1 "schema" = 1 bucket namespace
}

// QueryRows is not supported for S3 sources.
// Use the ingest tool to move data into Iceberg first, then query via mcp-sql-executor.
func (c *S3Connector) QueryRows(_ context.Context, _ string, _ int) ([]map[string]interface{}, error) {
	return nil, fmt.Errorf("direct SQL queries not supported for S3/MinIO; use the ingest tool to load data into Iceberg")
}

// GetRowCount is not available for object-store sources.
func (c *S3Connector) GetRowCount(_ context.Context, _ string) (int64, error) {
	return 0, fmt.Errorf("row count not available for S3/MinIO sources; profile after ingestion into Iceberg")
}

// GetColumns is not available without Iceberg metadata.
func (c *S3Connector) GetColumns(_ context.Context, _ string) ([]ColumnInfo, error) {
	return nil, fmt.Errorf("schema not available for S3/MinIO sources without Iceberg metadata; ingest first")
}

// Close is a no-op — minio.Client holds no long-lived connections.
func (c *S3Connector) Close() error { return nil }

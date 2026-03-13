// Package ingestion — IcebergWriter: writes NDJSON data to MinIO/Iceberg via the Nessie catalog.
// Day 11: MCP data connector service — MinIO/Iceberg sink for ingestion pipeline.
//
// Protocols: MCP
// SOLID: SRP (writes data only), DIP (accepts rows as []map[string]interface{})
package ingestion

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"

	"github.com/minio/minio-go/v7"
	miniocreds "github.com/minio/minio-go/v7/pkg/credentials"
)

// IcebergWriter serialises rows as NDJSON and stores them in MinIO.
// The resulting files can be registered as Iceberg data files via the Nessie REST catalog.
type IcebergWriter struct {
	client *minio.Client
	bucket string
}

// NewIcebergWriter creates an IcebergWriter connected to the given MinIO endpoint.
//
// Args:
//
//	endpoint  - MinIO host:port (e.g. "minio:9000")
//	accessKey - MinIO access key
//	secretKey - MinIO secret key
//	bucket    - target bucket (must already exist)
//	useSSL    - whether to use TLS for the MinIO connection
func NewIcebergWriter(endpoint, accessKey, secretKey, bucket string, useSSL bool) (*IcebergWriter, error) {
	client, err := minio.New(endpoint, &minio.Options{
		Creds:  miniocreds.NewStaticV4(accessKey, secretKey, ""),
		Secure: useSSL,
	})
	if err != nil {
		return nil, fmt.Errorf("create minio client for iceberg writer: %w", err)
	}
	return &IcebergWriter{client: client, bucket: bucket}, nil
}

// WriteNDJSON serialises rows as newline-delimited JSON (one JSON object per line)
// and uploads the result to MinIO at the given object path.
//
// Returns the number of bytes written on success.
//
// Args:
//
//	ctx  - context for the MinIO put operation
//	path - object key inside the bucket (e.g. "tenant_a/raw/orders/orders_job_42.ndjson")
//	rows - data rows as a slice of column→value maps
func (w *IcebergWriter) WriteNDJSON(ctx context.Context, path string, rows []map[string]interface{}) (int64, error) {
	if len(rows) == 0 {
		return 0, nil
	}

	var buf bytes.Buffer
	for _, row := range rows {
		b, err := json.Marshal(row)
		if err != nil {
			// Skip un-serialisable rows; don't abort the whole batch
			continue
		}
		buf.Write(b)
		buf.WriteByte('\n')
	}

	data := buf.Bytes()
	if len(data) == 0 {
		return 0, fmt.Errorf("no serialisable rows to write")
	}

	reader := bytes.NewReader(data)
	_, err := w.client.PutObject(ctx, w.bucket, path, reader, int64(len(data)), minio.PutObjectOptions{
		ContentType: "application/x-ndjson",
	})
	if err != nil {
		return 0, fmt.Errorf("minio put %s/%s: %w", w.bucket, path, err)
	}
	return int64(len(data)), nil
}

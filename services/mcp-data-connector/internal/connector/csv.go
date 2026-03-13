// Package connector — CSV/local file connector implementation.
// Day 11: MCP data connector service — csv IConnector.
//
// Protocols: MCP
// SOLID: OCP (implements IConnector without modifying base.go), SRP (CSV only)
package connector

import (
	"context"
	"encoding/csv"
	"fmt"
	"io"
	"os"
)

// CSVConnector implements IConnector for local CSV files.
// Column types are always reported as "string"; cast at analysis time.
type CSVConnector struct {
	filePath string
	headers  []string
}

// SourceType returns "csv".
func (c *CSVConnector) SourceType() string { return "csv" }

// Connect opens the CSV file and reads the header row.
//
// Required config key: file_path — absolute path to the CSV file.
func (c *CSVConnector) Connect(_ context.Context, config map[string]interface{}) (int, error) {
	path, _ := config["file_path"].(string)
	if path == "" {
		return 0, fmt.Errorf("file_path required for CSV connector")
	}

	f, err := os.Open(path) //nolint:gosec
	if err != nil {
		return 0, fmt.Errorf("open csv file: %w", err)
	}
	defer f.Close()

	reader := csv.NewReader(f)
	headers, err := reader.Read()
	if err != nil {
		return 0, fmt.Errorf("read csv headers: %w", err)
	}
	if len(headers) == 0 {
		return 0, fmt.Errorf("csv file has no columns")
	}

	c.filePath = path
	c.headers = headers
	return 1, nil // 1 "schema" = 1 file
}

// QueryRows reads up to limit data rows from the CSV file.
// The query parameter is ignored — all rows are returned (up to limit).
func (c *CSVConnector) QueryRows(_ context.Context, _ string, limit int) ([]map[string]interface{}, error) {
	if c.filePath == "" {
		return nil, fmt.Errorf("not connected; call Connect first")
	}

	f, err := os.Open(c.filePath) //nolint:gosec
	if err != nil {
		return nil, fmt.Errorf("open csv file: %w", err)
	}
	defer f.Close()

	reader := csv.NewReader(f)
	reader.Read() //nolint:errcheck // skip header row

	var rows []map[string]interface{}
	for i := 0; i < limit; i++ {
		record, err := reader.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			continue // skip malformed rows
		}
		row := make(map[string]interface{}, len(c.headers))
		for j, h := range c.headers {
			if j < len(record) {
				row[h] = record[j]
			} else {
				row[h] = nil
			}
		}
		rows = append(rows, row)
	}
	return rows, nil
}

// GetRowCount scans the entire file counting data rows (excluding header).
func (c *CSVConnector) GetRowCount(_ context.Context, _ string) (int64, error) {
	if c.filePath == "" {
		return 0, fmt.Errorf("not connected")
	}

	f, err := os.Open(c.filePath) //nolint:gosec
	if err != nil {
		return 0, fmt.Errorf("open csv file: %w", err)
	}
	defer f.Close()

	reader := csv.NewReader(f)
	// Start at -1 so that the header row brings us to 0 before any data rows
	count := int64(-1)
	for {
		_, err := reader.Read()
		if err == io.EOF {
			break
		}
		count++
	}
	if count < 0 {
		count = 0
	}
	return count, nil
}

// GetColumns returns one ColumnInfo per CSV header; all types reported as "string".
func (c *CSVConnector) GetColumns(_ context.Context, _ string) ([]ColumnInfo, error) {
	if c.filePath == "" {
		return nil, fmt.Errorf("not connected")
	}
	cols := make([]ColumnInfo, len(c.headers))
	for i, h := range c.headers {
		cols[i] = ColumnInfo{Name: h, DataType: "string"}
	}
	return cols, nil
}

// Close is a no-op — files are opened and closed per operation.
func (c *CSVConnector) Close() error { return nil }

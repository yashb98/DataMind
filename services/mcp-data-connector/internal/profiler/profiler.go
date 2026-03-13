// Package profiler — Schema profiler with lightweight PII detection.
// Day 11: MCP data connector service — profile_schema tool backend.
//
// Protocols: MCP
// SOLID: SRP (profiling only), DIP (depends on IConnector ABC, not concrete types)
// Benchmark: tests/benchmarks/bench_profiler.go
package profiler

import (
	"context"
	"fmt"
	"regexp"
	"time"

	"github.com/yashb98/datamind/mcp-data-connector/internal/connector"
	"github.com/yashb98/datamind/mcp-data-connector/internal/models"
)

// piiPatterns maps PII type labels to column-name regexes.
// Inspired by Microsoft Presidio's recogniser library; lightweight Go port.
// Column names matching these patterns are flagged as potentially containing PII.
var piiPatterns = map[string]*regexp.Regexp{
	"EMAIL":       regexp.MustCompile(`(?i)(email|e_mail|e_mail_address|mail)`),
	"PHONE":       regexp.MustCompile(`(?i)(phone|mobile|cell|tel|telephone|fax)`),
	"SSN":         regexp.MustCompile(`(?i)(ssn|social_security|national_id|taxpayer_id|tax_id|nin)`),
	"CREDIT_CARD": regexp.MustCompile(`(?i)(card_number|credit_card|debit_card|cvv|cvc|pan)`),
	"PERSON_NAME": regexp.MustCompile(`(?i)(first_name|last_name|full_name|surname|given_name|middle_name|display_name)`),
	"ADDRESS":     regexp.MustCompile(`(?i)(address|street|addr|zip|postal_code|postcode|city|state|country)`),
	"IP_ADDRESS":  regexp.MustCompile(`(?i)(ip_address|ip_addr|remote_addr|client_ip|source_ip)`),
	"DATE_OF_BIRTH": regexp.MustCompile(`(?i)(dob|date_of_birth|birth_date|birthday|birthdate)`),
	"GENDER":      regexp.MustCompile(`(?i)(gender|sex|pronouns)`),
	"PASSPORT":    regexp.MustCompile(`(?i)(passport|passport_number|passport_no)`),
	"LICENSE":     regexp.MustCompile(`(?i)(driver_license|driving_licence|license_number|licence_no)`),
	"BANK_ACCOUNT": regexp.MustCompile(`(?i)(account_number|iban|bic|swift|routing_number)`),
}

// SchemaProfiler profiles a data source table: row count, column statistics, and PII detection.
// SOLID DIP: depends on connector.IConnector, not on any concrete connector type.
type SchemaProfiler struct{}

// Profile retrieves column metadata and a data sample from conn, then computes
// null percentage, cardinality, and PII flags for each column.
//
// Args:
//
//	ctx        - context for database calls (honours cancellation/deadline)
//	conn       - active IConnector (already Connected)
//	tableName  - unqualified table name
//	sampleRows - number of rows to sample for statistics (capped by source availability)
//
// Returns:
//
//	*models.ProfileResponse with per-column statistics, or an error if the source is unreachable.
func (p *SchemaProfiler) Profile(
	ctx context.Context,
	conn connector.IConnector,
	tableName string,
	sampleRows int,
) (*models.ProfileResponse, error) {
	if sampleRows <= 0 {
		sampleRows = 1000
	}

	// 1. Retrieve column metadata
	columns, err := conn.GetColumns(ctx, tableName)
	if err != nil {
		return nil, fmt.Errorf("get columns for %q: %w", tableName, err)
	}
	if len(columns) == 0 {
		return nil, fmt.Errorf("table %q has no columns or does not exist", tableName)
	}

	// 2. Get total row count (best-effort; -1 for streaming sources)
	rowCount, _ := conn.GetRowCount(ctx, tableName)

	// 3. Sample rows for per-column statistics
	query := fmt.Sprintf("SELECT * FROM %s", tableName) //nolint:gosec
	rows, _ := conn.QueryRows(ctx, query, sampleRows)   // ignore error — partial data is ok

	// 4. Build per-column profiles
	colProfiles := make([]models.ColumnProfile, len(columns))
	for i, col := range columns {
		cp := models.ColumnProfile{
			Name: col.Name,
			Type: col.DataType,
		}

		// PII detection: column name pattern matching (Presidio-inspired)
		for piiType, pattern := range piiPatterns {
			if pattern.MatchString(col.Name) {
				cp.PIIDetected = true
				cp.PIIType = piiType
				break
			}
		}

		// Compute null percentage and distinct-value cardinality from sample rows
		if len(rows) > 0 {
			nullCount := 0
			uniqueVals := make(map[string]struct{}, len(rows))
			for _, row := range rows {
				val := row[col.Name]
				if val == nil {
					nullCount++
				} else {
					uniqueVals[fmt.Sprint(val)] = struct{}{}
				}
			}
			cp.NullPct = float64(nullCount) / float64(len(rows)) * 100.0
			cp.Cardinality = int64(len(uniqueVals))
		}

		colProfiles[i] = cp
	}

	return &models.ProfileResponse{
		TableName:  tableName,
		RowCount:   rowCount,
		Columns:    colProfiles,
		ProfiledAt: time.Now().UTC(),
	}, nil
}

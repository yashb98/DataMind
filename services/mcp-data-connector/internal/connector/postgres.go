// Package connector — PostgreSQL connector implementation.
// Day 11: MCP data connector service — postgres IConnector.
//
// Protocols: MCP
// SOLID: OCP (implements IConnector without modifying base.go), SRP (postgres only)
package connector

import (
	"context"
	"database/sql"
	"fmt"

	_ "github.com/lib/pq" // PostgreSQL driver registration
)

// PostgresConnector implements IConnector for PostgreSQL databases.
// Uses the standard database/sql interface with the lib/pq driver.
type PostgresConnector struct {
	db *sql.DB
}

// SourceType returns "postgres".
func (c *PostgresConnector) SourceType() string { return "postgres" }

// Connect opens a PostgreSQL connection using the provided config map.
//
// Required config keys: host, database, user, password.
// Optional: port (default 5432), sslmode (default "disable").
func (c *PostgresConnector) Connect(ctx context.Context, config map[string]interface{}) (int, error) {
	host, _ := config["host"].(string)
	port, _ := config["port"].(float64)
	dbname, _ := config["database"].(string)
	user, _ := config["user"].(string)
	password, _ := config["password"].(string)
	sslmode, ok := config["sslmode"].(string)
	if !ok || sslmode == "" {
		sslmode = "disable"
	}
	if port == 0 {
		port = 5432
	}

	dsn := fmt.Sprintf(
		"host=%s port=%d dbname=%s user=%s password=%s sslmode=%s",
		host, int(port), dbname, user, password, sslmode,
	)

	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return 0, fmt.Errorf("open postgres: %w", err)
	}

	if err := db.PingContext(ctx); err != nil {
		db.Close() //nolint:errcheck
		return 0, fmt.Errorf("ping postgres: %w", err)
	}
	c.db = db

	// Count user-defined schemas (excludes system schemas)
	row := db.QueryRowContext(ctx,
		"SELECT COUNT(*) FROM information_schema.schemata "+
			"WHERE schema_name NOT IN ('pg_catalog','information_schema','pg_toast')",
	)
	var count int
	if err := row.Scan(&count); err != nil {
		count = 1
	}
	return count, nil
}

// QueryRows executes query and returns up to limit rows as maps.
// The query is wrapped in a subquery so LIMIT is applied uniformly.
func (c *PostgresConnector) QueryRows(ctx context.Context, query string, limit int) ([]map[string]interface{}, error) {
	if c.db == nil {
		return nil, fmt.Errorf("not connected; call Connect first")
	}
	wrapped := fmt.Sprintf("SELECT * FROM (%s) _q LIMIT %d", query, limit)
	rows, err := c.db.QueryContext(ctx, wrapped)
	if err != nil {
		return nil, fmt.Errorf("query rows: %w", err)
	}
	defer rows.Close()
	return scanRows(rows)
}

// GetRowCount returns COUNT(*) for tableName.
func (c *PostgresConnector) GetRowCount(ctx context.Context, tableName string) (int64, error) {
	if c.db == nil {
		return 0, fmt.Errorf("not connected")
	}
	var count int64
	err := c.db.QueryRowContext(ctx,
		fmt.Sprintf("SELECT COUNT(*) FROM %s", tableName), //nolint:gosec
	).Scan(&count)
	return count, err
}

// GetColumns returns column names and data types from information_schema.
func (c *PostgresConnector) GetColumns(ctx context.Context, tableName string) ([]ColumnInfo, error) {
	if c.db == nil {
		return nil, fmt.Errorf("not connected")
	}
	rows, err := c.db.QueryContext(ctx,
		`SELECT column_name, data_type
		   FROM information_schema.columns
		  WHERE table_name = $1
		  ORDER BY ordinal_position`,
		tableName,
	)
	if err != nil {
		return nil, fmt.Errorf("get columns: %w", err)
	}
	defer rows.Close()

	var cols []ColumnInfo
	for rows.Next() {
		var col ColumnInfo
		if err := rows.Scan(&col.Name, &col.DataType); err != nil {
			continue
		}
		cols = append(cols, col)
	}
	return cols, rows.Err()
}

// Close closes the underlying database connection pool.
func (c *PostgresConnector) Close() error {
	if c.db != nil {
		return c.db.Close()
	}
	return nil
}

// ─── shared helpers ──────────────────────────────────────────────────────────

// scanRows converts sql.Rows into a slice of column-name→value maps.
// Used by both PostgresConnector and MySQLConnector.
func scanRows(rows *sql.Rows) ([]map[string]interface{}, error) {
	columns, err := rows.Columns()
	if err != nil {
		return nil, fmt.Errorf("get column names: %w", err)
	}

	var result []map[string]interface{}
	for rows.Next() {
		vals := make([]interface{}, len(columns))
		valPtrs := make([]interface{}, len(columns))
		for i := range vals {
			valPtrs[i] = &vals[i]
		}
		if err := rows.Scan(valPtrs...); err != nil {
			continue
		}
		row := make(map[string]interface{}, len(columns))
		for i, col := range columns {
			row[col] = vals[i]
		}
		result = append(result, row)
	}
	return result, rows.Err()
}

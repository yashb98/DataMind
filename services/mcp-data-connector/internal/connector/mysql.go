// Package connector — MySQL connector implementation.
// Day 11: MCP data connector service — mysql IConnector.
//
// Protocols: MCP
// SOLID: OCP (implements IConnector without modifying base.go), SRP (mysql only)
package connector

import (
	"context"
	"database/sql"
	"fmt"

	_ "github.com/go-sql-driver/mysql" // MySQL driver registration
)

// MySQLConnector implements IConnector for MySQL/MariaDB databases.
// Uses the standard database/sql interface with the go-sql-driver/mysql driver.
type MySQLConnector struct {
	db *sql.DB
}

// SourceType returns "mysql".
func (c *MySQLConnector) SourceType() string { return "mysql" }

// Connect opens a MySQL connection using the provided config map.
//
// Required config keys: host, database, user, password.
// Optional: port (default 3306).
func (c *MySQLConnector) Connect(ctx context.Context, config map[string]interface{}) (int, error) {
	host, _ := config["host"].(string)
	port, _ := config["port"].(float64)
	dbname, _ := config["database"].(string)
	user, _ := config["user"].(string)
	password, _ := config["password"].(string)

	if port == 0 {
		port = 3306
	}
	if host == "" {
		host = "localhost"
	}

	// DSN format: user:password@tcp(host:port)/dbname?parseTime=true
	dsn := fmt.Sprintf("%s:%s@tcp(%s:%d)/%s?parseTime=true&timeout=10s",
		user, password, host, int(port), dbname,
	)

	db, err := sql.Open("mysql", dsn)
	if err != nil {
		return 0, fmt.Errorf("open mysql: %w", err)
	}

	if err := db.PingContext(ctx); err != nil {
		db.Close() //nolint:errcheck
		return 0, fmt.Errorf("ping mysql: %w", err)
	}
	c.db = db

	// Count schemas visible to the connecting user (excludes system DBs)
	row := db.QueryRowContext(ctx,
		`SELECT COUNT(*)
		   FROM information_schema.schemata
		  WHERE schema_name NOT IN ('information_schema','mysql','performance_schema','sys')`,
	)
	var count int
	if err := row.Scan(&count); err != nil {
		count = 1
	}
	return count, nil
}

// QueryRows executes query and returns up to limit rows as maps.
func (c *MySQLConnector) QueryRows(ctx context.Context, query string, limit int) ([]map[string]interface{}, error) {
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
func (c *MySQLConnector) GetRowCount(ctx context.Context, tableName string) (int64, error) {
	if c.db == nil {
		return 0, fmt.Errorf("not connected")
	}
	var count int64
	err := c.db.QueryRowContext(ctx,
		fmt.Sprintf("SELECT COUNT(*) FROM `%s`", tableName), //nolint:gosec
	).Scan(&count)
	return count, err
}

// GetColumns returns column names and data types from information_schema.
func (c *MySQLConnector) GetColumns(ctx context.Context, tableName string) ([]ColumnInfo, error) {
	if c.db == nil {
		return nil, fmt.Errorf("not connected")
	}
	rows, err := c.db.QueryContext(ctx,
		`SELECT column_name, data_type
		   FROM information_schema.columns
		  WHERE table_name = ?
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
func (c *MySQLConnector) Close() error {
	if c.db != nil {
		return c.db.Close()
	}
	return nil
}

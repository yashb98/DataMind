// Package connector — ConnectorRegistry: thread-safe store of active connections.
// Day 11: MCP data connector service — Central connection registry.
//
// Protocols: MCP
// SOLID: SRP (registry manages lifecycle only), OCP (NewConnector factory is the extension point)
package connector

import (
	"fmt"
	"sync"
)

// ConnectorRegistry stores active connections indexed by connection_id.
// All methods are safe for concurrent access from multiple goroutines.
type ConnectorRegistry struct {
	mu    sync.RWMutex
	conns map[string]IConnector
}

// NewConnectorRegistry creates an empty ConnectorRegistry.
func NewConnectorRegistry() *ConnectorRegistry {
	return &ConnectorRegistry{
		conns: make(map[string]IConnector),
	}
}

// Register stores conn under the given id, replacing any previous entry.
func (r *ConnectorRegistry) Register(id string, conn IConnector) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.conns[id] = conn
}

// Get retrieves a registered connector by id.
// Returns an error if id is not found.
func (r *ConnectorRegistry) Get(id string) (IConnector, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	conn, ok := r.conns[id]
	if !ok {
		return nil, fmt.Errorf("connection %q not found; call connect tool first", id)
	}
	return conn, nil
}

// Remove closes and removes the connector registered under id.
// No-op if id is not registered.
func (r *ConnectorRegistry) Remove(id string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if conn, ok := r.conns[id]; ok {
		conn.Close() //nolint:errcheck
		delete(r.conns, id)
	}
}

// Len returns the number of active connections.
func (r *ConnectorRegistry) Len() int {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return len(r.conns)
}

// NewConnector instantiates a fresh (unconnected) connector for the given sourceType.
//
// SOLID OCP: To add a new source type, add a new case here and create a new
// file implementing IConnector — no existing connector files are touched.
func NewConnector(sourceType string) (IConnector, error) {
	switch sourceType {
	case "postgres":
		return &PostgresConnector{}, nil
	case "mysql":
		return &MySQLConnector{}, nil
	case "s3", "minio":
		return &S3Connector{}, nil
	case "kafka":
		return &KafkaConnector{}, nil
	case "csv":
		return &CSVConnector{}, nil
	case "bigquery":
		return &BigQueryConnector{}, nil
	case "snowflake":
		return &SnowflakeConnector{}, nil
	default:
		return nil, fmt.Errorf("unsupported source type %q; supported: postgres, mysql, s3, kafka, csv, bigquery, snowflake", sourceType)
	}
}

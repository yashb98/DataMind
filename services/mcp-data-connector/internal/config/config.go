// Package config — Environment-based configuration for mcp-data-connector.
// Day 11: MCP data connector service — Config from env vars.
//
// Protocols: MCP
// SOLID: SRP (config loading only), DIP (Config struct injected into all components)
package config

import (
	"os"
	"strconv"
)

// Config holds all runtime configuration for the mcp-data-connector service.
// Values are loaded from environment variables with sensible defaults for local development.
type Config struct {
	Port        int
	ServiceName string

	// MinIO/Iceberg
	MinIOEndpoint  string
	MinIOAccessKey string
	MinIOSecretKey string
	MinIOBucket    string
	MinIOSecure    bool

	// Nessie catalog
	NessieEndpoint string

	// OTel
	OtelEndpoint string

	// Max connections per tenant
	MaxConnections int
}

// Load reads configuration from environment variables.
// All fields have defaults suitable for Docker Compose development.
func Load() *Config {
	port, _ := strconv.Atoi(getEnv("PORT", "8100"))
	maxConn, _ := strconv.Atoi(getEnv("MAX_CONNECTIONS", "10"))

	return &Config{
		Port:           port,
		ServiceName:    "mcp-data-connector",
		MinIOEndpoint:  getEnv("MINIO_ENDPOINT", "minio:9000"),
		MinIOAccessKey: getEnv("MINIO_ACCESS_KEY", "minioadmin"),
		MinIOSecretKey: getEnv("MINIO_SECRET_KEY", "minioadmin123"),
		MinIOBucket:    getEnv("MINIO_BUCKET", "datamind-iceberg"),
		MinIOSecure:    getEnv("MINIO_SECURE", "false") == "true",
		NessieEndpoint: getEnv("NESSIE_ENDPOINT", "http://nessie:19120"),
		OtelEndpoint:   getEnv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317"),
		MaxConnections: maxConn,
	}
}

func getEnv(key, defaultValue string) string {
	if v, ok := os.LookupEnv(key); ok {
		return v
	}
	return defaultValue
}

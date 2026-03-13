// Package connector — Apache Kafka connector implementation.
// Day 11: MCP data connector service — kafka IConnector.
//
// Protocols: MCP
// SOLID: OCP (implements IConnector without modifying base.go), SRP (kafka only)
package connector

import (
	"context"
	"fmt"
	"time"

	"github.com/segmentio/kafka-go"
)

// KafkaConnector implements IConnector for Apache Kafka topics.
// QueryRows reads up to limit messages from partition 0 of the configured topic.
type KafkaConnector struct {
	brokers []string
	topic   string
}

// SourceType returns "kafka".
func (c *KafkaConnector) SourceType() string { return "kafka" }

// Connect verifies broker connectivity and reads partition metadata for the topic.
//
// Required config keys: topic.
// Optional: brokers ([]string, default ["kafka:9092"]).
func (c *KafkaConnector) Connect(ctx context.Context, config map[string]interface{}) (int, error) {
	brokersRaw, _ := config["brokers"].([]interface{})
	topic, _ := config["topic"].(string)
	if topic == "" {
		return 0, fmt.Errorf("topic required for Kafka connector")
	}

	brokerList := make([]string, 0, len(brokersRaw))
	for _, b := range brokersRaw {
		if s, ok := b.(string); ok {
			brokerList = append(brokerList, s)
		}
	}
	if len(brokerList) == 0 {
		brokerList = []string{"kafka:9092"}
	}

	// Test connectivity: dial the first broker and read partition metadata
	conn, err := kafka.DialContext(ctx, "tcp", brokerList[0])
	if err != nil {
		return 0, fmt.Errorf("kafka dial %s: %w", brokerList[0], err)
	}
	defer conn.Close()

	conn.SetDeadline(time.Now().Add(5 * time.Second)) //nolint:errcheck
	partitions, err := conn.ReadPartitions(topic)
	if err != nil {
		return 0, fmt.Errorf("read partitions for topic %q: %w", topic, err)
	}

	c.brokers = brokerList
	c.topic = topic
	return len(partitions), nil // schema_count = partition count for Kafka
}

// QueryRows reads up to limit messages from partition 0 of the configured topic.
// Each message is returned as a map with keys: key, value, offset, partition, timestamp.
// The query parameter is ignored for Kafka sources.
func (c *KafkaConnector) QueryRows(ctx context.Context, _ string, limit int) ([]map[string]interface{}, error) {
	if len(c.brokers) == 0 {
		return nil, fmt.Errorf("not connected; call Connect first")
	}
	reader := kafka.NewReader(kafka.ReaderConfig{
		Brokers:   c.brokers,
		Topic:     c.topic,
		Partition: 0,
		MaxBytes:  10e6, // 10 MiB
	})
	defer reader.Close()

	var rows []map[string]interface{}
	for i := 0; i < limit; i++ {
		msg, err := reader.ReadMessage(ctx)
		if err != nil {
			break // EOF or context cancelled
		}
		rows = append(rows, map[string]interface{}{
			"key":       string(msg.Key),
			"value":     string(msg.Value),
			"offset":    msg.Offset,
			"partition": msg.Partition,
			"timestamp": msg.Time.UTC().Format(time.RFC3339),
		})
	}
	return rows, nil
}

// GetRowCount returns -1 for streaming sources — the count is unbounded.
func (c *KafkaConnector) GetRowCount(_ context.Context, _ string) (int64, error) {
	return -1, nil
}

// GetColumns returns the fixed schema of a Kafka message envelope.
func (c *KafkaConnector) GetColumns(_ context.Context, _ string) ([]ColumnInfo, error) {
	return []ColumnInfo{
		{Name: "key", DataType: "string"},
		{Name: "value", DataType: "string"},
		{Name: "offset", DataType: "int64"},
		{Name: "partition", DataType: "int"},
		{Name: "timestamp", DataType: "timestamp"},
	}, nil
}

// Close is a no-op — the reader is created per-query and closed in QueryRows.
func (c *KafkaConnector) Close() error { return nil }

#!/usr/bin/env bash
# Idempotent topic bootstrap for the 8 logical Kafka topics this platform
# uses (see docs/architecture.md - deliberately not one topic per
# status/retry variant; retry is DB-driven, not a Kafka topic).
set -euo pipefail

: "${KAFKA_BOOTSTRAP_SERVERS:?}"

# Dispatch + message-events: 48h retention - durable backlog buffer to
# survive a multi-hour Kannel outage and catch up, not a permanent log.
declare -A SHORT_RETENTION_TOPICS=(
  [campaign.dispatch.sms]="12"
  [campaign.dispatch.ivr]="12"
  [campaign.dispatch.doctor]="12"
  [campaign.message-events]="12"
)
SHORT_RETENTION_MS=172800000  # 48h

# Lifecycle/analytics topics: 14 days - replay/debug/backfill window.
declare -A LONG_RETENTION_TOPICS=(
  [campaign.import.events]="6"
  [campaign.audience.events]="6"
  [campaign.subscription-events]="6"
  [campaign.analytics.events]="6"
)
LONG_RETENTION_MS=1209600000  # 14 days

# DLQ topics only for the 3 dispatch topics + message-events: 90 days,
# a manual ops review window.
DLQ_TOPICS=(
  "campaign.dispatch.sms.dlq"
  "campaign.dispatch.ivr.dlq"
  "campaign.dispatch.doctor.dlq"
  "campaign.message-events.dlq"
)
DLQ_RETENTION_MS=7776000000  # 90 days

echo "Waiting for Kafka at ${KAFKA_BOOTSTRAP_SERVERS}..."
for i in $(seq 1 30); do
  if /opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

for topic in "${!SHORT_RETENTION_TOPICS[@]}"; do
  partitions="${SHORT_RETENTION_TOPICS[$topic]}"
  echo "Ensuring topic '$topic' (partitions=$partitions, retention=48h)..."
  /opt/kafka/bin/kafka-topics.sh --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" \
    --create --if-not-exists \
    --topic "$topic" --partitions "$partitions" --replication-factor 1 \
    --config retention.ms=$SHORT_RETENTION_MS
done

for topic in "${!LONG_RETENTION_TOPICS[@]}"; do
  partitions="${LONG_RETENTION_TOPICS[$topic]}"
  echo "Ensuring topic '$topic' (partitions=$partitions, retention=14d)..."
  /opt/kafka/bin/kafka-topics.sh --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" \
    --create --if-not-exists \
    --topic "$topic" --partitions "$partitions" --replication-factor 1 \
    --config retention.ms=$LONG_RETENTION_MS
done

for topic in "${DLQ_TOPICS[@]}"; do
  echo "Ensuring DLQ topic '$topic' (retention=90d)..."
  /opt/kafka/bin/kafka-topics.sh --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" \
    --create --if-not-exists \
    --topic "$topic" --partitions 6 --replication-factor 1 \
    --config retention.ms=$DLQ_RETENTION_MS
done

echo "Kafka topic bootstrap complete."
/opt/kafka/bin/kafka-topics.sh --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" --list

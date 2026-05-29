#!/usr/bin/env bash
set -euo pipefail

BASE_URL="http://localhost:8000/ar5"
ENDPOINT="$BASE_URL/processes/add_border_split_surface/execution"

CLOSED_RING='[10.3850,63.4305],[10.3860,63.4305],[10.3860,63.4315],[10.3850,63.4315],[10.3850,63.4305]'

# Vertical line through the middle of the rectangle, extending past both edges
SPLIT_LINE='[10.3855,63.4300],[10.3855,63.4320]'

CRS='{"type":"name","properties":{"name":"EPSG:4326"}}'

echo "=== Step 1: closed ring → should create a surface ==="
curl -s -X POST "$ENDPOINT" \
  -H "Content-Type: application/json" \
  -d "{
    \"inputs\": {
      \"feature\": {
        \"value\": {
          \"type\": \"Feature\",
          \"geometry\": {
            \"type\": \"LineString\",
            \"crs\": $CRS,
            \"coordinates\": [$CLOSED_RING]
          },
          \"properties\": {}
        },
        \"mediaType\": \"application/geo+json\"
      }
    },
    \"outputs\": {
      \"changelog\": { \"transmissionMode\": \"value\" },
      \"summary\":   { \"transmissionMode\": \"value\" }
    },
    \"response\": \"document\"
  }" | jq .

echo ""
echo "=== Step 2: line through middle → should split the surface ==="
curl -s -X POST "$ENDPOINT" \
  -H "Content-Type: application/json" \
  -d "{
    \"inputs\": {
      \"feature\": {
        \"value\": {
          \"type\": \"Feature\",
          \"geometry\": {
            \"type\": \"LineString\",
            \"coordinates\": [$SPLIT_LINE]
          },
          \"properties\": {}
        },
        \"mediaType\": \"application/geo+json\"
      }
    },
    \"outputs\": {
      \"changelog\": { \"transmissionMode\": \"value\" }
    },
    \"response\": \"document\"
  }" | jq .

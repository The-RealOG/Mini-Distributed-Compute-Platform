#!/bin/bash
# Test script for the Mini Distributed Compute Platform

set -e

COORDINATOR_URL="http://localhost:8000"
RUNNER_URL="http://localhost:8080"

echo "=== Testing Mini Distributed Compute Platform ==="
echo ""

# Check if services are running
echo "1. Checking service health..."
if ! curl -f -s "$COORDINATOR_URL/health" > /dev/null; then
    echo "ERROR: Coordinator service is not running"
    exit 1
fi

if ! curl -f -s "$RUNNER_URL/health" > /dev/null; then
    echo "ERROR: Runner service is not running"
    exit 1
fi

echo "✓ Services are healthy"
echo ""

# Test 1: Simple echo command
echo "2. Testing simple command execution..."
JOB_RESPONSE=$(curl -s -X POST "$COORDINATOR_URL/jobs" \
  -H "Content-Type: application/json" \
  -d '{"command": "echo hello world", "timeout": 10}')

JOB_ID=$(echo "$JOB_RESPONSE" | grep -o '"job_id":"[^"]*' | cut -d'"' -f4)
echo "  Job ID: $JOB_ID"

# Wait for job to complete
sleep 3

JOB_STATUS=$(curl -s "$COORDINATOR_URL/jobs/$JOB_ID")
echo "  Job Status: $JOB_STATUS"
echo ""

# Test 2: System information command
echo "3. Testing system information command..."
JOB_RESPONSE=$(curl -s -X POST "$COORDINATOR_URL/jobs" \
  -H "Content-Type: application/json" \
  -d '{"command": "uname -a", "timeout": 10}')

JOB_ID=$(echo "$JOB_RESPONSE" | grep -o '"job_id":"[^"]*' | cut -d'"' -f4)
echo "  Job ID: $JOB_ID"

sleep 3

JOB_STATUS=$(curl -s "$COORDINATOR_URL/jobs/$JOB_ID")
echo "  Job Status: $JOB_STATUS"
echo ""

# Test 3: CPU information
echo "4. Testing CPU information command..."
JOB_RESPONSE=$(curl -s -X POST "$COORDINATOR_URL/jobs" \
  -H "Content-Type: application/json" \
  -d '{"command": "cat /proc/cpuinfo | head -20", "timeout": 10}')

JOB_ID=$(echo "$JOB_RESPONSE" | grep -o '"job_id":"[^"]*' | cut -d'"' -f4)
echo "  Job ID: $JOB_ID"

sleep 3

JOB_STATUS=$(curl -s "$COORDINATOR_URL/jobs/$JOB_ID")
echo "  Job Status: $JOB_STATUS"
echo ""

# Test 4: Metrics endpoint
echo "5. Testing metrics endpoint..."
METRICS=$(curl -s "$COORDINATOR_URL/metrics")
echo "$METRICS" | head -10
echo ""

# Test 5: Runner metrics
echo "6. Testing runner metrics endpoint..."
RUNNER_METRICS=$(curl -s "$RUNNER_URL/metrics")
echo "$RUNNER_METRICS"
echo ""

echo "=== All tests completed ==="

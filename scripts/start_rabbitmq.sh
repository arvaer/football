#!/bin/bash
# Start RabbitMQ server using podman

set -e

RABBITMQ_CONTAINER_NAME=${RABBITMQ_CONTAINER_NAME:-"transfermarkt-rabbitmq"}
RABBITMQ_PORT=${RABBITMQ_PORT:-"5672"}
RABBITMQ_MGMT_PORT=${RABBITMQ_MGMT_PORT:-"15672"}

# If --ocker is passed, use docker instead of podman
if [[ "$1" == "--docker" ]]; then
    PODMAN="docker"
else
    PODMAN="podman"
fi

echo "Starting RabbitMQ server..."
echo "Container: $RABBITMQ_CONTAINER_NAME"
echo "AMQP Port: $RABBITMQ_PORT"
echo "Management UI Port: $RABBITMQ_MGMT_PORT"

# Check if container already exists
if $PODMAN ps -a --format '{{.Names}}' | grep -q "^${RABBITMQ_CONTAINER_NAME}$"; then
    echo "Container $RABBITMQ_CONTAINER_NAME already exists, starting it..."
    $PODMAN start "$RABBITMQ_CONTAINER_NAME"
else
    echo "Creating new RabbitMQ container..."
    $PODMAN run -d \
        --name "$RABBITMQ_CONTAINER_NAME" \
        -p "$RABBITMQ_PORT:5672" \
        -p "$RABBITMQ_MGMT_PORT:15672" \
        -e RABBITMQ_DEFAULT_USER=guest \
        -e RABBITMQ_DEFAULT_PASS=guest \
        docker.io/library/rabbitmq:3-management
fi

echo ""
echo "RabbitMQ started successfully!"
echo "AMQP URL: amqp://guest:guest@localhost:$RABBITMQ_PORT/"
echo "Management UI: http://localhost:$RABBITMQ_MGMT_PORT/"
echo "Default credentials: guest/guest"

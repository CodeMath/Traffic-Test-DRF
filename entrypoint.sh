#!/bin/bash
set -e

# 환경변수 기본값 설정
WORKER_CLASS=${WORKER_CLASS:-gthread}
WORKERS=${WORKERS:-3}
THREADS=${THREADS:-3}
WORKER_CONNECTIONS=${WORKER_CONNECTIONS:-1000}
MAX_REQUESTS=${MAX_REQUESTS:-1200}
MAX_REQUESTS_JITTER=${MAX_REQUESTS_JITTER:-50}
TIMEOUT=${TIMEOUT:-30}
GRACEFUL_TIMEOUT=${GRACEFUL_TIMEOUT:-30}
KEEP_ALIVE=${KEEP_ALIVE:-5}
LOG_LEVEL=${LOG_LEVEL:-info}
BIND_ADDRESS=${BIND_ADDRESS:-0.0.0.0:8882}

echo "========================================="
echo "Starting Gunicorn with configuration:"
echo "  Worker Class: $WORKER_CLASS"
echo "  Workers: $WORKERS"

# worker class에 따른 설정 분기
if [ "$WORKER_CLASS" = "gevent" ]; then
    echo "  Worker Connections: $WORKER_CONNECTIONS"
    echo "  Total Capacity: $((WORKERS * WORKER_CONNECTIONS)) concurrent connections"
    echo "========================================="

    exec gunicorn config.wsgi:application \
        --bind "$BIND_ADDRESS" \
        --workers "$WORKERS" \
        --worker-class gevent \
        --worker-connections "$WORKER_CONNECTIONS" \
        --worker-tmp-dir /dev/shm \
        --max-requests "$MAX_REQUESTS" \
        --max-requests-jitter "$MAX_REQUESTS_JITTER" \
        --timeout "$TIMEOUT" \
        --graceful-timeout "$GRACEFUL_TIMEOUT" \
        --keep-alive "$KEEP_ALIVE" \
        --log-level "$LOG_LEVEL" \
        --access-logfile - \
        --error-logfile - \
        --name traffics

elif [ "$WORKER_CLASS" = "gthread" ]; then
    echo "  Threads per Worker: $THREADS"
    echo "  Total Capacity: $((WORKERS * THREADS)) concurrent threads"
    echo "========================================="

    exec gunicorn config.wsgi:application \
        --bind "$BIND_ADDRESS" \
        --workers "$WORKERS" \
        --threads "$THREADS" \
        --worker-class gthread \
        --worker-tmp-dir /dev/shm \
        --max-requests "$MAX_REQUESTS" \
        --max-requests-jitter "$MAX_REQUESTS_JITTER" \
        --timeout "$TIMEOUT" \
        --graceful-timeout "$GRACEFUL_TIMEOUT" \
        --keep-alive "$KEEP_ALIVE" \
        --log-level "$LOG_LEVEL" \
        --access-logfile - \
        --error-logfile - \
        --name traffics

else
    echo "Error: Unknown WORKER_CLASS '$WORKER_CLASS'"
    echo "Supported values: gthread, gevent"
    exit 1
fi

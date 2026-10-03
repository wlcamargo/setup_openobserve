"""Send telemetry while simulating a database connection and queries."""

from __future__ import annotations

import logging
import random
import time

from opentelemetry import metrics, trace

from otel_example import configure_telemetry


SERVICE_NAME = "python-db-connector-example"
STREAM_NAME = "python-db-demo"

DB_SYSTEM = "postgresql"
DB_NAME = "orders_db"
DB_HOST = "db.internal.local"
DB_PORT = 5432

QUERIES = [
    ("SELECT", "SELECT * FROM customers WHERE id = %s"),
    ("SELECT", "SELECT * FROM orders WHERE status = 'pending'"),
    ("INSERT", "INSERT INTO orders (customer_id, total) VALUES (%s, %s)"),
    ("UPDATE", "UPDATE orders SET status = 'shipped' WHERE id = %s"),
    ("DELETE", "DELETE FROM sessions WHERE expires_at < now()"),
]

TOTAL_QUERIES = 10
SLOW_QUERY_THRESHOLD_SECONDS = 0.5
CONNECTION_FAILURE_RATE = 0.1


def simulate_connect(logger: logging.Logger) -> None:
    logger.info(
        "Connecting to database %s at %s:%s", DB_NAME, DB_HOST, DB_PORT
    )
    time.sleep(random.uniform(0.05, 0.2))

    if random.random() < CONNECTION_FAILURE_RATE:
        logger.error(
            "Connection attempt to %s:%s timed out; retrying", DB_HOST, DB_PORT
        )
        time.sleep(random.uniform(0.1, 0.3))

    logger.info("Connected to database %s", DB_NAME)


def main() -> None:
    tracer_provider, meter_provider, logger_provider = configure_telemetry(STREAM_NAME)
    tracer = trace.get_tracer(SERVICE_NAME)
    meter = metrics.get_meter(SERVICE_NAME)
    logger = logging.getLogger(SERVICE_NAME)

    active_connections = meter.create_up_down_counter(
        "db_demo.connections.active",
        description="Number of active database connections",
        unit="{connection}",
    )
    query_counter = meter.create_counter(
        "db_demo.queries",
        description="Number of database queries executed",
        unit="{query}",
    )
    query_error_counter = meter.create_counter(
        "db_demo.query.errors",
        description="Number of database queries that failed",
        unit="{query}",
    )
    query_duration = meter.create_histogram(
        "db_demo.query.duration",
        description="Duration of each database query",
        unit="s",
    )

    started_at = time.perf_counter()
    try:
        with tracer.start_as_current_span("db-connect") as connect_span:
            connect_span.set_attribute("db.system", DB_SYSTEM)
            connect_span.set_attribute("db.name", DB_NAME)
            connect_span.set_attribute("net.peer.name", DB_HOST)
            connect_span.set_attribute("net.peer.port", DB_PORT)

            simulate_connect(logger)
            active_connections.add(1)

            for query_number in range(1, TOTAL_QUERIES + 1):
                operation, statement = random.choice(QUERIES)
                query_started_at = time.perf_counter()

                with tracer.start_as_current_span(f"db-query-{operation.lower()}") as query_span:
                    query_span.set_attribute("db.system", DB_SYSTEM)
                    query_span.set_attribute("db.name", DB_NAME)
                    query_span.set_attribute("db.operation", operation)
                    query_span.set_attribute("db.statement", statement)

                    logger.info("Query %s: %s", query_number, statement)
                    time.sleep(random.uniform(0.05, 0.7))
                    elapsed_seconds = time.perf_counter() - query_started_at

                    if random.random() < 0.15:
                        query_span.set_status(trace.StatusCode.ERROR)
                        logger.error(
                            "Query %s failed: %s (duration=%.3fs)",
                            query_number,
                            statement,
                            elapsed_seconds,
                        )
                        query_error_counter.add(1, {"operation": operation})
                    elif elapsed_seconds > SLOW_QUERY_THRESHOLD_SECONDS:
                        logger.warning(
                            "Query %s was slow: %.3fs (statement=%s)",
                            query_number,
                            elapsed_seconds,
                            statement,
                        )
                    else:
                        logger.info(
                            "Query %s completed in %.3fs", query_number, elapsed_seconds
                        )

                    query_duration.record(elapsed_seconds, {"operation": operation})
                    query_counter.add(1, {"operation": operation})
                    query_span.set_attribute("db.query.duration_seconds", elapsed_seconds)

            active_connections.add(-1)
            logger.info("Closing connection to database %s", DB_NAME)

        total_seconds = time.perf_counter() - started_at
        tracer_provider.force_flush()
        meter_provider.force_flush()
        logger_provider.force_flush()
        print(
            f"Simulated {TOTAL_QUERIES} queries in {total_seconds:.1f}s "
            f"to stream {STREAM_NAME}"
        )
    finally:
        logger_provider.shutdown()
        meter_provider.shutdown()
        tracer_provider.shutdown()


if __name__ == "__main__":
    main()

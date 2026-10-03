"""Send example logs, traces, and metrics to OpenObserve over OTLP/HTTP."""

from __future__ import annotations

import base64
import logging
import os
import time

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


OPENOBSERVE_URL = os.getenv(
    "OPENOBSERVE_URL", "http://localhost:5080/api/default"
).rstrip("/")
OPENOBSERVE_EMAIL = os.getenv("OPENOBSERVE_EMAIL", "chapolin@chapolin.com")
OPENOBSERVE_PASSWORD = os.getenv("OPENOBSERVE_PASSWORD", "Mudar@1234")
OPENOBSERVE_STREAM = os.getenv("OPENOBSERVE_STREAM", "python-sample")
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "python-sample")


def auth_headers(stream_name: str | None = None) -> dict[str, str]:
    credentials = f"{OPENOBSERVE_EMAIL}:{OPENOBSERVE_PASSWORD}".encode()
    authorization = base64.b64encode(credentials).decode()
    return {
        "Authorization": f"Basic {authorization}",
        "stream-name": stream_name or OPENOBSERVE_STREAM,
    }


def configure_telemetry(
    stream_name: str | None = None,
) -> tuple[TracerProvider, MeterProvider, LoggerProvider]:
    resource = Resource.create(
        {
            "service.name": SERVICE_NAME,
            "service.version": "1.0.0",
            "deployment.environment": "local",
        }
    )
    headers = auth_headers(stream_name)

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=f"{OPENOBSERVE_URL}/v1/traces",
                headers=headers,
            )
        )
    )
    trace.set_tracer_provider(tracer_provider)

    metric_exporter = OTLPMetricExporter(
        endpoint=f"{OPENOBSERVE_URL}/v1/metrics",
        headers=headers,
    )
    metric_reader = PeriodicExportingMetricReader(
        metric_exporter,
        export_interval_millis=5_000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(
                endpoint=f"{OPENOBSERVE_URL}/v1/logs",
                headers=headers,
            )
        )
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(
        LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
    )

    return tracer_provider, meter_provider, logger_provider


def main() -> None:
    tracer_provider, meter_provider, logger_provider = configure_telemetry()
    tracer = trace.get_tracer(SERVICE_NAME)
    meter = metrics.get_meter(SERVICE_NAME)
    request_counter = meter.create_counter(
        "demo.requests",
        description="Number of demo requests processed",
        unit="{request}",
    )
    request_duration = meter.create_histogram(
        "demo.request.duration",
        description="Demo request duration",
        unit="ms",
    )
    logger = logging.getLogger(SERVICE_NAME)

    try:
        with tracer.start_as_current_span("demo-operation") as span:
            span.set_attribute("demo.operation", "send-telemetry")
            logger.info("Demo log sent to OpenObserve", extra={"demo": True})

            start = time.perf_counter()
            request_counter.add(1, {"route": "/demo"})
            time.sleep(0.05)
            request_duration.record(
                (time.perf_counter() - start) * 1_000,
                {"route": "/demo"},
            )
            span.add_event("demo-operation-complete")

        tracer_provider.force_flush()
        meter_provider.force_flush()
        logger_provider.force_flush()
        print(
            f"Telemetry sent: service={SERVICE_NAME}, "
            f"stream={OPENOBSERVE_STREAM}, endpoint={OPENOBSERVE_URL}"
        )
    finally:
        logger_provider.shutdown()
        meter_provider.shutdown()
        tracer_provider.shutdown()


if __name__ == "__main__":
    main()

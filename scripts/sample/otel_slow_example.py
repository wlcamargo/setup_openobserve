"""Send telemetry while simulating a slow process for at least 45 seconds."""

from __future__ import annotations

import logging
import time

from opentelemetry import metrics, trace

from otel_example import configure_telemetry


TOTAL_STAGES = 3
STAGE_DELAY_SECONDS = 15
SERVICE_NAME = "python-otel-slow-example"
STREAM_NAME = "python-slow-demo"


def main() -> None:
    tracer_provider, meter_provider, logger_provider = configure_telemetry(STREAM_NAME)
    tracer = trace.get_tracer(SERVICE_NAME)
    meter = metrics.get_meter(SERVICE_NAME)
    logger = logging.getLogger(SERVICE_NAME)

    stage_counter = meter.create_counter(
        "slow_demo.stages",
        description="Number of slow demo stages completed",
        unit="{stage}",
    )
    warning_counter = meter.create_counter(
        "slow_demo.warnings",
        description="Number of simulated warnings",
        unit="{warning}",
    )
    error_counter = meter.create_counter(
        "slow_demo.errors",
        description="Number of simulated errors",
        unit="{error}",
    )
    stage_duration = meter.create_histogram(
        "slow_demo.stage.duration",
        description="Duration of each slow demo stage",
        unit="s",
    )

    started_at = time.perf_counter()
    try:
        with tracer.start_as_current_span("slow-process") as process_span:
            process_span.set_attribute("demo.total_stages", TOTAL_STAGES)
            process_span.set_attribute("demo.stage_delay_seconds", STAGE_DELAY_SECONDS)
            logger.info("Slow demo started; expected duration is at least 45 seconds")

            for stage_number in range(1, TOTAL_STAGES + 1):
                stage_name = f"stage-{stage_number}"
                stage_started_at = time.perf_counter()

                with tracer.start_as_current_span(stage_name) as stage_span:
                    stage_span.set_attribute("demo.stage_number", stage_number)
                    logger.info("Stage %s started", stage_number)

                    logger.warning(
                        "Stage %s is intentionally slow and may need attention",
                        stage_number,
                    )
                    warning_counter.add(1, {"stage": stage_name})

                    logger.error(
                        "Stage %s simulated an error event; processing continues",
                        stage_number,
                    )
                    error_counter.add(1, {"stage": stage_name})

                    time.sleep(STAGE_DELAY_SECONDS)
                    elapsed_seconds = time.perf_counter() - stage_started_at
                    stage_duration.record(
                        elapsed_seconds,
                        {"stage": stage_name},
                    )
                    stage_counter.add(1, {"stage": stage_name})
                    stage_span.set_attribute("demo.stage_duration_seconds", elapsed_seconds)
                    logger.info(
                        "Stage %s completed after %.1f seconds",
                        stage_number,
                        elapsed_seconds,
                    )

            total_seconds = time.perf_counter() - started_at
            process_span.set_attribute("demo.total_duration_seconds", total_seconds)
            logger.info("Slow demo completed after %.1f seconds", total_seconds)

        tracer_provider.force_flush()
        meter_provider.force_flush()
        logger_provider.force_flush()
        print(
            f"Slow telemetry sent after {total_seconds:.1f} seconds "
            f"to stream {STREAM_NAME}"
        )
    finally:
        logger_provider.shutdown()
        meter_provider.shutdown()
        tracer_provider.shutdown()


if __name__ == "__main__":
    main()

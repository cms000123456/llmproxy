from __future__ import annotations

"""OpenTelemetry distributed tracing configuration for LLM Proxy."""

import os
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import SpanKind, Status, StatusCode

from .logging_config import get_logger

logger = get_logger(__name__)


def setup_tracing(
    service_name: str = "llmproxy",
    otlp_endpoint: str | None = None,
    enabled: bool = True,
    console_export: bool = False,
) -> trace.TracerProvider | None:
    """Set up OpenTelemetry tracing.

    Args:
        service_name: Name of the service for tracing
        otlp_endpoint: OTLP HTTP endpoint URL (e.g., http://jaeger:4318/v1/traces)
        enabled: Whether tracing is enabled
        console_export: Also export spans to console (for debugging)

    Returns:
        Configured TracerProvider or None if disabled
    """
    if not enabled:
        logger.info("Tracing disabled")
        return None

    # Auto-detect endpoint from environment if not provided
    if otlp_endpoint is None:
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318/v1/traces")

    # Create resource
    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: "0.1.0",
            "deployment.environment": os.getenv("ENVIRONMENT", "development"),
        }
    )

    # Create provider
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    # Add OTLP exporter
    try:
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        logger.info(f"Tracing enabled with OTLP endpoint: {otlp_endpoint}")
    except Exception as e:
        logger.warning(f"Failed to create OTLP exporter: {e}")
        # Still create provider without exporter for manual tracing

    # Add console exporter for debugging
    if console_export:
        console_exporter = ConsoleSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(console_exporter))
        logger.info("Console span exporter enabled")

    return provider


def get_tracer(name: str = "llmproxy") -> trace.Tracer:
    """Get a tracer instance.

    Args:
        name: Tracer name (typically __name__)

    Returns:
        Tracer instance
    """
    return trace.get_tracer(name)


class TracingContext:
    """Context manager for creating spans."""

    def __init__(
        self,
        tracer: trace.Tracer,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: dict[str, Any] | None = None,
    ):
        self.tracer = tracer
        self.name = name
        self.kind = kind
        self.attributes = attributes or {}
        self.span: trace.Span | None = None

    def __enter__(self) -> trace.Span:
        self.span = self.tracer.start_span(self.name, kind=self.kind)
        for key, value in self.attributes.items():
            self.span.set_attribute(key, value)
        return self.span

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.span:
            if exc_val:
                self.span.set_status(Status(StatusCode.ERROR, str(exc_val)))
                self.span.record_exception(exc_val)
            self.span.end()


def trace_operation(
    tracer: trace.Tracer,
    operation: str,
    model: str | None = None,
    **attributes: Any,
) -> TracingContext:
    """Create a tracing context for an operation.

    Args:
        tracer: Tracer instance
        operation: Operation name (e.g., "chat_completion", "cache_lookup")
        model: Model name (if applicable)
        **attributes: Additional span attributes

    Returns:
        TracingContext for use with 'with' statement
    """
    attrs = {"operation": operation}
    if model:
        attrs["model"] = model
    attrs.update(attributes)

    return TracingContext(
        tracer=tracer,
        name=operation,
        kind=SpanKind.INTERNAL,
        attributes=attrs,
    )

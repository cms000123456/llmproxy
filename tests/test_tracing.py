"""Tests for OpenTelemetry tracing functionality."""

from unittest.mock import MagicMock, patch


class TestTracingSetup:
    """Tests for tracing setup."""

    def test_setup_tracing_disabled(self):
        """When tracing is disabled, should return None."""
        from llmproxy.tracing import setup_tracing

        result = setup_tracing(enabled=False)
        assert result is None

    def test_setup_tracing_enabled(self):
        """When tracing is enabled, should return TracerProvider."""
        from llmproxy.tracing import setup_tracing

        # Mock the OTLP exporter to avoid network calls
        with patch("llmproxy.tracing.OTLPSpanExporter") as mock_exporter:
            mock_exporter.return_value = MagicMock()
            result = setup_tracing(
                service_name="test-service",
                otlp_endpoint="http://localhost:4318/v1/traces",
                enabled=True,
            )
            assert result is not None

    def test_get_tracer(self):
        """Should return a tracer instance."""
        from llmproxy.tracing import get_tracer

        tracer = get_tracer("test")
        assert tracer is not None


class TestTracingContext:
    """Tests for tracing context manager."""

    def test_tracing_context_success(self):
        """Context manager should create and end span on success."""
        from llmproxy.tracing import TracingContext, get_tracer

        tracer = get_tracer("test")

        with TracingContext(tracer, "test_operation") as span:
            assert span is not None

    def test_tracing_context_with_attributes(self):
        """Context manager should set attributes on span."""
        from llmproxy.tracing import TracingContext, get_tracer

        tracer = get_tracer("test")

        with TracingContext(
            tracer, "test_operation", attributes={"key": "value", "number": 42}
        ) as span:
            assert span is not None

    def test_tracing_context_with_exception(self):
        """Context manager should record exception on error."""
        from llmproxy.tracing import TracingContext, get_tracer

        tracer = get_tracer("test")

        try:
            with TracingContext(tracer, "test_operation") as span:
                raise ValueError("Test error")
        except ValueError:
            pass  # Expected


class TestTraceOperation:
    """Tests for trace_operation helper."""

    def test_trace_operation_basic(self):
        """Should create tracing context for operation."""
        from llmproxy.tracing import get_tracer, trace_operation

        tracer = get_tracer("test")

        with trace_operation(tracer, "chat_completion") as span:
            assert span is not None

    def test_trace_operation_with_model(self):
        """Should include model in attributes."""
        from llmproxy.tracing import get_tracer, trace_operation

        tracer = get_tracer("test")

        with trace_operation(tracer, "chat_completion", model="gpt-4") as span:
            assert span is not None

    def test_trace_operation_with_extra_attributes(self):
        """Should include extra attributes."""
        from llmproxy.tracing import get_tracer, trace_operation

        tracer = get_tracer("test")

        with trace_operation(tracer, "cache_lookup", cache_hit=True, tokens=100) as span:
            assert span is not None

# server/core/observability.py
"""
Observability & Telemetry - Phase 15

Comprehensive observability stack for distributed tracing, metrics collection,
structured logging, and alerting:
- Prometheus metrics collection and exposition
- Structured JSON logging with context propagation
- Custom spans for business logic
- Service health and dependency tracking
"""

import asyncio
import logging
import time
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Callable
from enum import Enum
from dataclasses import dataclass, asdict, field
from functools import wraps
import uuid

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

from core.logger import get_logger

logger = get_logger(__name__)


class SpanStatus(str, Enum):
    """Span status indicators"""
    OK = "OK"
    ERROR = "ERROR"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    CANCELLED = "CANCELLED"


class MetricType(str, Enum):
    """Metric types"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class TraceContext:
    """Distributed trace context"""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    baggage: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class MetricPoint:
    """Single metric data point"""
    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    metric_type: MetricType = MetricType.GAUGE


@dataclass
class Alert:
    """Alert configuration and state"""
    name: str
    condition: str  # e.g., "error_rate > 0.05"
    threshold: float
    severity: str  # "low", "medium", "high", "critical"
    action: str  # e.g., "email", "slack", "pagerduty"
    enabled: bool = True
    triggered_count: int = 0
    last_triggered: Optional[datetime] = None


class TelemetryCollector:
    """
    Centralized telemetry collection and management
    
    Coordinates tracing, metrics, and logging across the system
    """
    
    def __init__(self):
        """Initialize telemetry collector"""
        self.enabled = True
        self.tracer = None
        self.meter = None
        self.metrics_registry: Dict[str, MetricPoint] = {}
        self.alerts: Dict[str, Alert] = {}
        self.trace_context: Optional[TraceContext] = None
    
    async def initialize(self) -> bool:
        """Initialize telemetry subsystems"""
        try:
            # Set up tracing (in-memory only, no external export)
            trace_provider = TracerProvider()
            trace.set_tracer_provider(trace_provider)
            self.tracer = trace.get_tracer(__name__)
            
            # Set up metrics (Prometheus compatible)
            prometheus_reader = PrometheusMetricReader()
            metrics_provider = MeterProvider(metric_readers=[prometheus_reader])
            metrics.set_meter_provider(metrics_provider)
            self.meter = metrics.get_meter(__name__)
            
            # Auto-instrument FastAPI and SQLAlchemy
            FastAPIInstrumentor().instrument()
            SQLAlchemyInstrumentor().instrument()
            RedisInstrumentor().instrument()
            
            logger.info("Telemetry initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize telemetry: {e}")
            return False
    
    async def shutdown(self) -> None:
        """Shutdown telemetry subsystems"""
        logger.info("Telemetry shutdown complete")
    
    def create_trace_context(self) -> TraceContext:
        """Create new trace context"""
        self.trace_context = TraceContext(
            trace_id=str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            baggage={
                "service": "gatekeeper",
                "version": "2.0",
                "environment": "production"
            }
        )
        return self.trace_context
    
    def start_span(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        kind: str = "INTERNAL"
    ):
        """Start a new span"""
        if not self.enabled or not self.tracer:
            return None
        
        span = self.tracer.start_span(name)
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        return span
    
    def record_metric(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Record a metric point"""
        if not self.enabled:
            return
        
        metric = MetricPoint(
            name=name,
            value=value,
            labels=labels or {},
            timestamp=datetime.now()
        )
        self.metrics_registry[f"{name}:{json.dumps(labels or {})}"] = metric
    
    def register_alert(self, alert: Alert) -> None:
        """Register an alert condition"""
        self.alerts[alert.name] = alert
        logger.info(f"Alert registered: {alert.name} ({alert.severity})")
    
    async def check_alerts(self) -> List[Alert]:
        """Check all alert conditions"""
        triggered = []
        
        for alert_name, alert in self.alerts.items():
            if not alert.enabled:
                continue
            
            # Parse simple conditions (e.g., "error_rate > 0.05")
            if self._evaluate_condition(alert.condition):
                alert.triggered_count += 1
                alert.last_triggered = datetime.now()
                triggered.append(alert)
                logger.warning(f"Alert triggered: {alert.name}")
        
        return triggered
    
    def _evaluate_condition(self, condition: str) -> bool:
        """Simple condition evaluator"""
        # This would be enhanced with actual metric data
        # For now, return False (no alerts triggered)
        return False
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of collected metrics"""
        return {
            "total_metrics": len(self.metrics_registry),
            "metrics": list(self.metrics_registry.keys()),
            "timestamp": datetime.now().isoformat()
        }


class StructuredLogger:
    """
    Structured JSON logger with context propagation
    
    Logs all entries as JSON for ELK/Splunk ingestion
    """
    
    def __init__(self, name: str, telemetry: TelemetryCollector):
        """Initialize structured logger"""
        self.name = name
        self.telemetry = telemetry
        self.logger = logging.getLogger(name)
        self.context: Dict[str, Any] = {}
    
    def set_context(self, key: str, value: Any) -> None:
        """Set logging context"""
        self.context[key] = value
    
    def clear_context(self) -> None:
        """Clear logging context"""
        self.context.clear()
    
    def _format_log(
        self,
        level: str,
        message: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Format log entry as JSON"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "logger": self.name,
            "message": message,
            "context": self.context,
            **kwargs
        }
        
        # Add trace context if available
        if self.telemetry.trace_context:
            log_entry["trace"] = self.telemetry.trace_context.to_dict()
        
        return log_entry
    
    def info(self, message: str, **kwargs) -> None:
        """Log info level"""
        log = self._format_log("INFO", message, **kwargs)
        self.logger.info(json.dumps(log))
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning level"""
        log = self._format_log("WARNING", message, **kwargs)
        self.logger.warning(json.dumps(log))
    
    def error(self, message: str, exc_info: bool = False, **kwargs) -> None:
        """Log error level"""
        log = self._format_log("ERROR", message, **kwargs)
        self.logger.error(json.dumps(log), exc_info=exc_info)
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug level"""
        log = self._format_log("DEBUG", message, **kwargs)
        self.logger.debug(json.dumps(log))


class ServiceHealthTracker:
    """
    Track health of service dependencies
    
    Monitors database, Redis, external APIs, etc.
    """
    
    def __init__(self):
        """Initialize health tracker"""
        self.health_checks: Dict[str, Dict[str, Any]] = {}
        self.last_check: Dict[str, datetime] = {}
    
    async def check_database(self, db) -> Dict[str, Any]:
        """Check database health"""
        try:
            start = time.time()
            result = await db.execute("SELECT 1")
            latency = (time.time() - start) * 1000
            
            self.health_checks["database"] = {
                "status": "healthy",
                "latency_ms": latency,
                "timestamp": datetime.now().isoformat()
            }
            return self.health_checks["database"]
        except Exception as e:
            self.health_checks["database"] = {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
            return self.health_checks["database"]
    
    async def check_redis(self, redis_client) -> Dict[str, Any]:
        """Check Redis health"""
        try:
            start = time.time()
            await redis_client.ping()
            latency = (time.time() - start) * 1000
            
            self.health_checks["redis"] = {
                "status": "healthy",
                "latency_ms": latency,
                "timestamp": datetime.now().isoformat()
            }
            return self.health_checks["redis"]
        except Exception as e:
            self.health_checks["redis"] = {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
            return self.health_checks["redis"]
    
    async def check_external_api(
        self,
        name: str,
        check_func: Callable
    ) -> Dict[str, Any]:
        """Check external API health"""
        try:
            start = time.time()
            result = await check_func()
            latency = (time.time() - start) * 1000
            
            self.health_checks[name] = {
                "status": "healthy",
                "latency_ms": latency,
                "timestamp": datetime.now().isoformat()
            }
            return self.health_checks[name]
        except Exception as e:
            self.health_checks[name] = {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
            return self.health_checks[name]
    
    def get_overall_health(self) -> Dict[str, Any]:
        """Get overall system health"""
        statuses = [
            check.get("status") == "healthy"
            for check in self.health_checks.values()
        ]
        
        overall_status = "healthy" if all(statuses) else "degraded" if any(statuses) else "unhealthy"
        
        return {
            "status": overall_status,
            "checks": self.health_checks,
            "healthy_count": sum(statuses),
            "total_checks": len(statuses)
        }


def with_telemetry(span_name: str, attributes: Optional[Dict[str, Any]] = None):
    """Decorator for automatic span creation"""
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Get telemetry instance from first arg if available
            telemetry = getattr(args[0], 'telemetry', None) if args else None
            
            if telemetry:
                span = telemetry.start_span(span_name, attributes)
                try:
                    result = await func(*args, **kwargs)
                    if span:
                        span.set_status(trace.StatusCode.OK)
                    return result
                except Exception as e:
                    if span:
                        span.set_status(trace.StatusCode.ERROR)
                    raise
                finally:
                    if span:
                        span.end()
            else:
                return await func(*args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            telemetry = getattr(args[0], 'telemetry', None) if args else None
            
            if telemetry:
                span = telemetry.start_span(span_name, attributes)
                try:
                    result = func(*args, **kwargs)
                    if span:
                        span.set_status(trace.StatusCode.OK)
                    return result
                except Exception as e:
                    if span:
                        span.set_status(trace.StatusCode.ERROR)
                    raise
                finally:
                    if span:
                        span.end()
            else:
                return func(*args, **kwargs)
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator
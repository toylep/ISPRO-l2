from fastapi import FastAPI, Request, Response
from pydantic import BaseModel
from enum import Enum
import random
import time
import logging
import json

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST, REGISTRY

# --- OpenTelemetry ---
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

_resource = Resource.create({"service.name": "washer-service", "service.version": "0.0.1"})
_provider = TracerProvider(resource=_resource)
_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint="http://jaeger:4318/v1/traces"))
)
trace.set_tracer_provider(_provider)
tracer = trace.get_tracer("washer")


# --- Настройка логирования (JSON → stdout → Docker → Promtail → Loki) ---

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        obj: dict = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Добавляем trace_id/span_id если есть активный спан (корреляция логов и трейсов)
        ctx = trace.get_current_span().get_span_context()
        if ctx.is_valid:
            obj["trace_id"] = format(ctx.trace_id, "032x")
            obj["span_id"] = format(ctx.span_id, "016x")
        # Дополнительные поля из extra={}
        skip = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message", "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in skip:
                obj[key] = value
        return json.dumps(obj, ensure_ascii=False)


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())

for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi", "washer"):
    log = logging.getLogger(name)
    log.handlers = [handler]
    log.setLevel(logging.INFO)
    log.propagate = False

logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger("washer")


# --- Приложение ---

app = FastAPI(
    title="Прачка сервис",
    description="Сервис по бронированию стиральных машин.",
    version="0.0.1",
)

# Инструментируем FastAPI — автоматически создаёт спаны для каждого запроса
FastAPIInstrumentor.instrument_app(app)


# --- Метрики ---

http_requests_total = Counter(
    "http_requests_total",
    "Общее количество HTTP запросов",
    ["method", "path", "status_code"],
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "Длительность HTTP запросов в секундах",
    ["method", "path"],
)
washer_bookings_total = Counter(
    "washer_bookings_total",
    "Общее количество бронирований стиральных машин",
    ["washer_id"],
)
washer_state_changes_total = Counter(
    "washer_state_changes_total",
    "Количество смен состояния стиральных машин",
    ["washer_id", "new_state"],
)


@app.middleware("http")
async def metrics_and_logging_middleware(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)

    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start

    path = request.url.path
    method = request.method
    status = response.status_code

    http_requests_total.labels(method=method, path=path, status_code=status).inc()
    http_request_duration_seconds.labels(method=method, path=path).observe(duration)
    logger.info(
        "http request",
        extra={"http_method": method, "http_path": path, "http_status": status, "duration_ms": round(duration * 1000, 2)},
    )
    return response


@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


# --- Модели ---

class WasherState(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    BROKEN = "broken"


class WasherIn(BaseModel):
    state: WasherState


class WasherOut(WasherIn):
    id: int


class WasherBookIn(BaseModel):
    washer_id: int
    hours: int


class WasherBookOut(WasherBookIn):
    id: int


# --- Эндпоинты ---

@app.get("/washers", response_model=list[WasherOut])
async def get_washers():
    """Получение списка стиральных машин"""
    states = [WasherState.AVAILABLE, WasherState.UNAVAILABLE, WasherState.BROKEN]
    return [WasherOut(id=i, state=states[i % len(states)]) for i in range(10)]


@app.post("/washers/book", response_model=WasherBookOut)
async def book_washer(body: WasherBookIn):
    """Бронирование стиральной машины"""
    with tracer.start_as_current_span("book_washer") as span:
        span.set_attribute("washer.id", body.washer_id)
        span.set_attribute("washer.hours", body.hours)

        booking_id = random.randint(0, 100)
        span.set_attribute("booking.id", booking_id)

        washer_bookings_total.labels(washer_id=str(body.washer_id)).inc()
        logger.info(
            "washer booked",
            extra={"washer_id": body.washer_id, "hours": body.hours, "booking_id": booking_id},
        )
        return WasherBookOut(id=booking_id, washer_id=body.washer_id, hours=body.hours)


@app.get("/washers/my-books", response_model=list[WasherBookOut])
async def my_books():
    """Просмотр бронирований"""
    return [WasherBookOut(id=i, washer_id=i % 5, hours=random.randint(1, 3)) for i in range(5)]


@app.put("/washers/{washer_id}", response_model=WasherOut)
async def change_state(washer_id: int, body: WasherIn):
    """Админская функция смены состояния"""
    with tracer.start_as_current_span("change_washer_state") as span:
        span.set_attribute("washer.id", washer_id)
        span.set_attribute("washer.new_state", body.state.value)

        washer_state_changes_total.labels(washer_id=str(washer_id), new_state=body.state.value).inc()
        logger.info(
            "washer state changed",
            extra={"washer_id": washer_id, "new_state": body.state.value},
        )
        return WasherOut(id=washer_id, state=body.state)

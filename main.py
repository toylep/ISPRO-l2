from fastapi import FastAPI, Request, Response
from pydantic import BaseModel
from enum import Enum
import random
import time
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST, REGISTRY

app = FastAPI(
    title="Прачка сервис",
    description="Сервис по бронированию стиральных машин. Цель показать что кодогенерация выглядит вполне естественно и удобно. Ручное редактирование OpenAPI лучше использовать в случае если такое требуют процессы, например использование монорепы с кучей проектов",
    version="0.0.1",
)

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

# Продуктовая метрика: количество бронирований стиральных машин
washer_bookings_total = Counter(
    "washer_bookings_total",
    "Общее количество бронирований стиральных машин",
    ["washer_id"],
)

# Продуктовая метрика: смены состояния машин (для отслеживания поломок/ремонта)
washer_state_changes_total = Counter(
    "washer_state_changes_total",
    "Количество смен состояния стиральных машин",
    ["washer_id", "new_state"],
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    http_requests_total.labels(
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
    ).inc()
    http_request_duration_seconds.labels(
        method=request.method,
        path=request.url.path,
    ).observe(duration)
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
    washer_bookings_total.labels(washer_id=str(body.washer_id)).inc()
    return WasherBookOut(id=random.randint(0, 100), washer_id=body.washer_id, hours=body.hours)


@app.get("/washers/my-books", response_model=list[WasherBookOut])
async def my_books():
    """Просмотр бронирований"""
    return [WasherBookOut(id=i, washer_id=i % 5, hours=random.randint(1, 3)) for i in range(5)]


@app.put("/washers/{washer_id}", response_model=WasherOut)
async def change_state(washer_id: int, body: WasherIn):
    """Админская функция смены состояния"""
    washer_state_changes_total.labels(washer_id=str(washer_id), new_state=body.state.value).inc()
    return WasherOut(id=washer_id, state=body.state)

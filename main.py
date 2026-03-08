from fastapi import FastAPI
from pydantic import BaseModel
from enum import Enum
import random 
app = FastAPI(
    title="Прачка сервис",
    description="Сервис по бронированию стиральных машин. Цель показать что кодогенерация выглядит вполне естественно и удобно. Ручное редактирование OpenAPI лучше использовать в случае если такое требуют процессы, например использование монорепы с кучей проектов",
    version="0.0.1",
)

class WasherState(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    BROKEN = "broken"

class WasherIn(BaseModel):
    state: WasherState

class WasherOut(WasherIn):
    id: int

class WasherBookIn(BaseModel):
    # id: int
    washer_id: int
    hours: int

class WasherBookOut(WasherBookIn):
    id: int
    
@app.get("/washers", response_model=list[WasherOut])
async def get_washers():
    """
    Получение списка стиральных машин
    """
    return [WasherOut(id=i, is_available=bool(i % 2)) for i in range(10)]

@app.post("/washers/book",response_model=WasherBookOut)
async def book_washer(body: WasherBookIn):
    """
    Бронирование стиральной машины
    """
    return WasherBookOut(id=random.randint(0,100), washer_id=body.washer_id,hours=body.hours)

@app.get("/washers/my-books", response_model=list[WasherOut])
async def my_books():
    """
    Просмотр бронирований
    """
    return [WasherOut(id=i, is_available=bool(i % 2)) for i in range(10)]

@app.put("/washers/{washer_id}",response_model=WasherOut)
async def change_state(washer_id: int,body: WasherIn):
    """
    Админская функция смены состояния
    """
    return WasherOut(id=washer_id,state=body.state)
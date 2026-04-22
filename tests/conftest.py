import os

# Отключаем OTLP-экспорт во время тестов — Jaeger недоступен вне Docker
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

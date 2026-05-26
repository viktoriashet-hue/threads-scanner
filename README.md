# 🔍 Threads Scanner

Реальный скрапер топовых постов из Threads по ключевым словам. Поиск с фильтрацией по дате, сортировкой по популярности или времени, экспортом в CSV.

## Возможности

- 🔎 Поиск по любому ключевому слову или фразе
- 📅 Фильтр по дате публикации
- 🔥 Сортировка: по популярности или по времени
- 📊 Метрики: лайки, ответы, репосты
- 💾 Экспорт результатов в CSV

## Деплой на Render.com (бесплатно)

1. Загрузи этот репозиторий на GitHub
2. Зайди на [render.com](https://render.com) и зарегистрируйся
3. Нажми **New → Web Service**
4. Подключи свой GitHub репозиторий
5. Укажи:
   - **Build Command:** `pip install -r requirements.txt && playwright install chromium && playwright install-deps chromium`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Нажми **Deploy** — через 3-5 минут получишь живую ссылку

## Локальный запуск

```bash
pip install -r requirements.txt
playwright install chromium
uvicorn main:app --reload
```

Открой http://localhost:8000

## Важно

Playwright-скрапер перехватывает GraphQL-запросы Threads. Meta может блокировать частые запросы — делай паузы между поисками.

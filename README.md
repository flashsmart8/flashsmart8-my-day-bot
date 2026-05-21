# Мій день — сервер

Персональний AI-помічник. Серверна частина на FastAPI.

## Запуск на Railway

### Змінні середовища (Railway → Variables)

```
ANTHROPIC_API_KEY=sk-ant-...
FIREBASE_API_KEY=...
FIREBASE_DB_URL=https://sklad-oblik-default-rtdb.europe-west1.firebasedatabase.app
FIREBASE_EMAIL=myday@flashsmart.local
FIREBASE_PASSWORD=...
JWT_SECRET=<випадковий рядок 32+ символи>
FCM_SERVER_KEY=...
ENCRYPTION_TRANSIT_KEY=<випадковий рядок 32+ символи>
ALLOWED_ORIGIN=https://flashsmart8.github.io
```

### Деплой

1. Створити репозиторій `my-day-bot` на GitHub
2. Завантажити всі файли
3. У Railway: New Project → Deploy from GitHub → `my-day-bot`
4. Додати змінні середовища
5. Railway автоматично побачить `Procfile` і запустить сервер

## Структура

```
main.py             — FastAPI: ендпоінти, Firebase, JWT
crypto_utils.py     — AES-256-GCM шифрування
ai_engine.py        — Claude API: парсинг намірів, брифінги
weather_service.py  — Open-Meteo API: погода, схід/захід
holidays.py         — українські свята та іменини
holidays_data.json  — база свят (JSON)
scheduler.py        — APScheduler: cron-задачі
push_service.py     — Firebase Cloud Messaging
```

## API ендпоінти

- `GET /health` — перевірка стану
- `GET /auth/challenge` — отримати challenge для Passkey
- `POST /auth/register` — реєстрація
- `POST /auth/login` — вхід через Passkey
- `POST /auth/pin-login` — вхід через PIN
- `POST /message` — надіслати повідомлення (зашифроване)
- `GET /briefing` — отримати брифінг
- `GET /today` — події і погода на сьогодні
- `GET /facts` — факти
- `GET /goals` — цілі
- `POST /push/register` — зареєструвати FCM токен

# Персональний AI-помічник — план проєкту

## Назва: "Мій день" (робоча)

PWA-додаток з AI-ядром для управління особистим життям: сім'я, здоров'я, побут, нагадування, емоційний стан. Захищений Passkey-автентифікацією і наскрізним шифруванням.

---

## Стек технологій

| Компонент | Технологія | Чому |
|---|---|---|
| Фронтенд | HTML/CSS/JS (один файл PWA) | Як sklad.html — знайомий підхід |
| Хостинг фронту | GitHub Pages | Вже налаштовано |
| Бекенд | Python (FastAPI) на Railway | Як flashsmart-bot |
| База даних | Firebase RTDB | Вже є інфраструктура |
| AI | Claude API (Sonnet) | Вже використовується в Олезі |
| Push-нотифікації | Firebase Cloud Messaging (FCM) | Безкоштовно, працює з PWA |
| Автентифікація | WebAuthn / Passkey | Ключ у Secure Enclave |
| Шифрування | Web Crypto API (AES-256-GCM) | Наскрізне, на пристрої |
| Погода | Open-Meteo API | Безкоштовно, без ключа, без реєстрації |
| Свята / іменини | Вбудований JSON | Без API, локальний файл |
| Схід/захід сонця | Open-Meteo (daily) | Приходить разом з погодою |

---

## Структура репозиторіїв

### Репозиторій 1: `my-day-app` (GitHub Pages)

```
my-day-app/
├── index.html          — PWA: чат, дашборд, налаштування
├── sw.js               — Service Worker (офлайн, push)
├── manifest.json       — PWA-маніфест (іконки, назва)
├── icons/
│   ├── icon-192.png
│   └── icon-512.png
└── README.md
```

### Репозиторій 2: `my-day-bot` (Railway)

```
my-day-bot/
├── main.py             — FastAPI сервер
├── crypto_utils.py     — серверне шифрування/розшифрування
├── ai_engine.py        — Claude API: парсинг намірів, генерація
├── scheduler.py        — APScheduler: брифінги, нагадування
├── push_service.py     — відправка push через FCM
├── weather_service.py  — погода, схід/захід сонця (Open-Meteo)
├── holidays.py         — українські свята, іменини, пам'ятні дати
├── holidays_data.json  — база свят і іменин (оновлюється вручну)
├── requirements.txt
├── Procfile            — web: uvicorn main:app --host 0.0.0.0 --port $PORT
└── README.md
```

---

## Firebase: структура бази

Окремий шлях `/myday` (не змішувати з `/sklad`).

```
/myday
  /user
    /profile          — зашифрований JSON (ім'я, місто, часовий пояс)
    /passkey           — публічний ключ WebAuthn (не секретний)
    /settings          — частота брифінгів, тиха година, мова
    /fcm_token         — токен для push-нотифікацій

  /facts
    /fact_001
      data: "U2FsdGVk..."        — зашифровано
      category: "family"          — НЕ зашифровано (для фільтрації)
      created: 1716200000000
    /fact_002
      data: "U2FsdGVk..."
      category: "health"
      created: 1716200100000

  /events
    /evt_001
      data: "U2FsdGVk..."        — зашифрований JSON (текст, час, повтор)
      date: "2026-05-22"          — НЕ зашифровано (для cron-запитів)
      done: false
      created: 1716200000000

  /journal
    /2026-05-20
      data: "U2FsdGVk..."        — зашифрований JSON (записи дня)
      mood: 3                     — НЕ зашифровано (1-5, для патернів)
      created: 1716200000000

  /goals
    /goal_001
      data: "U2FsdGVk..."        — зашифрований JSON (назва, опис)
      active: true
      created: 1716200000000
```

### Принцип шифрування

**Зашифровано (поле `data`):** текстовий зміст — імена, деталі здоров'я, тексти нагадувань, опис цілей. Те, що несе персональний сенс.

**НЕ зашифровано:** метадані для технічних запитів — `category`, `date`, `done`, `mood` (число 1-5), `active`, `created`. Ці дані потрібні серверу для cron-задач (знайти сьогоднішні нагадування) і не містять чутливої інформації.

---

## Passkey (WebAuthn) — як працює

### Реєстрація (один раз)

```
1. Користувач відкриває PWA вперше
2. PWA → сервер: "хочу зареєструватися"
3. Сервер генерує challenge (випадковий рядок)
4. PWA викликає navigator.credentials.create({
     publicKey: {
       challenge: challenge,
       rp: { name: "Мій день", id: "my-day-app.github.io" },
       user: { id: ..., name: "owner", displayName: "Власник" },
       pubKeyCredParams: [{ alg: -7, type: "public-key" }],
       authenticatorSelection: {
         authenticatorAttachment: "platform",  // тільки вбудований
         userVerification: "required"          // біометрія обов'язкова
       }
     }
   })
5. Телефон показує Touch ID / Face ID
6. Secure Enclave генерує пару ключів
7. Публічний ключ → сервер → Firebase /myday/user/passkey
8. Приватний ключ залишається в Secure Enclave НАЗАВЖДИ
```

### Вхід (кожного разу)

```
1. PWA → сервер: "хочу увійти"
2. Сервер генерує новий challenge
3. PWA викликає navigator.credentials.get({
     publicKey: {
       challenge: challenge,
       rpId: "my-day-app.github.io",
       userVerification: "required"
     }
   })
4. Телефон: Touch ID / Face ID
5. Secure Enclave підписує challenge приватним ключем
6. PWA → сервер: підпис + credentialId
7. Сервер перевіряє підпис публічним ключем з Firebase
8. Якщо OK → видає JWT токен (термін: 24 години)
9. PWA зберігає JWT в пам'яті (не localStorage!)
```

### Резервний вхід

PIN-код (6 цифр), який задається при реєстрації. Зберігається як bcrypt-хеш у Firebase. Використовується ТІЛЬКИ якщо біометрія не працює (мокрі руки, пошкоджений сенсор).

---

## Шифрування даних — як працює

### Генерація ключа шифрування (один раз при реєстрації)

```javascript
// 1. Генеруємо випадковий ключ шифрування
const encKey = await crypto.subtle.generateKey(
  { name: "AES-GCM", length: 256 },
  true,  // extractable — щоб зберегти
  ["encrypt", "decrypt"]
);

// 2. Експортуємо ключ у raw-формат
const rawKey = await crypto.subtle.exportKey("raw", encKey);

// 3. Шифруємо ключ за допомогою ключа, виведеного з пароля/PIN
const salt = crypto.getRandomValues(new Uint8Array(16));
const pinKey = await crypto.subtle.deriveKey(
  { name: "PBKDF2", salt, iterations: 600000, hash: "SHA-256" },
  await crypto.subtle.importKey("raw", new TextEncoder().encode(pin), "PBKDF2", false, ["deriveKey"]),
  { name: "AES-GCM", length: 256 },
  false,
  ["wrapKey", "unwrapKey"]
);

// 4. Обгортаємо (wrap) ключ шифрування
const iv = crypto.getRandomValues(new Uint8Array(12));
const wrappedKey = await crypto.subtle.wrapKey("raw", encKey, pinKey, { name: "AES-GCM", iv });

// 5. Зберігаємо wrappedKey + salt + iv в IndexedDB
//    Без PIN ніхто не розгорне ключ
```

### Шифрування повідомлення (кожного разу)

```javascript
async function encrypt(plaintext, encKey) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encoded = new TextEncoder().encode(plaintext);
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    encKey,
    encoded
  );
  // Повертаємо iv + ciphertext як base64
  const combined = new Uint8Array(iv.length + new Uint8Array(ciphertext).length);
  combined.set(iv);
  combined.set(new Uint8Array(ciphertext), iv.length);
  return btoa(String.fromCharCode(...combined));
}

async function decrypt(base64, encKey) {
  const combined = Uint8Array.from(atob(base64), c => c.charCodeAt(0));
  const iv = combined.slice(0, 12);
  const ciphertext = combined.slice(12);
  const decrypted = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv },
    encKey,
    ciphertext
  );
  return new TextDecoder().decode(decrypted);
}
```

### Потік даних при відправці повідомлення

```
Користувач пише: "завтра забрати дитину о 14:00"
        │
        ▼
PWA шифрує текст ключем з Secure Enclave
        │
        ▼
HTTPS POST → сервер (Railway)
  Body: { encrypted: "U2FsdGVk...", date: "2026-05-21" }
        │
        ▼
Сервер розшифровує (тимчасово, в пам'яті)
        │
        ▼
Claude API: витягує намір і факти
  → type: "event"
  → text: "забрати дитину"
  → time: "14:00"
  → date: "2026-05-21"
        │
        ▼
Сервер шифрує результат назад
        │
        ▼
Зберігає в Firebase:
  /events/evt_042: { data: "U2FsdGVk...", date: "2026-05-21", done: false }
        │
        ▼
Відповідь клієнту (зашифрована):
  "Записав. Нагадаю завтра о 13:30."
```

---

## API ендпоінти (FastAPI)

```python
# Автентифікація
POST /auth/register          — реєстрація Passkey
POST /auth/login             — вхід через Passkey
POST /auth/pin-login         — резервний вхід через PIN

# Повідомлення
POST /message                — надіслати повідомлення (зашифроване)
  → Claude парсить намір
  → зберігає факт/подію/журнал
  → повертає зашифровану відповідь

# Дашборд
GET  /briefing               — ранковий/вечірній брифінг (зашифрований)
GET  /today                  — події і нагадування на сьогодні

# Факти і цілі
GET  /facts                  — всі факти (зашифровані)
GET  /goals                  — всі цілі (зашифровані)

# Push
POST /push/register          — зберегти FCM токен
```

Всі ендпоінти (крім /auth/*) вимагають JWT токен у заголовку `Authorization: Bearer <token>`.

---

## Cron-задачі (APScheduler)

| Час | Задача | Опис |
|---|---|---|
| 07:30 | Ранковий брифінг | Погода + події дня + свята/іменини + схід/захід сонця + незакриті нагадування → Claude формує текст → push |
| 21:00 | Вечірній звіт | Що зроблено, що пропущено, настрій за тиждень, погода на завтра → push |
| Кожні 30 хв | Перевірка нагадувань | Чи є нагадування на найближчі 30 хв → push якщо є |
| Щонеділі 10:00 | Тижневий огляд | Патерни сну, настрою, незакриті цілі → push |
| 06:00 | Оновлення погоди | Запит Open-Meteo на добу вперед, кеш у пам'яті |

---

## PWA-інтерфейс (index.html)

### Три екрани (перемикання табами внизу)

**1. Чат** — основний екран
- Поле введення внизу (як месенджер)
- Історія повідомлень (зберігається локально, розшифровується на льоту)
- Відповіді помічника з м'яким стилем

**2. Дашборд** — огляд дня
- Погода зараз + прогноз на день (температура, дощ, вітер)
- Схід/захід сонця
- Свято або іменини сьогодні (якщо є)
- Наступна подія (картка)
- Активні нагадування (список)
- Настрій за тиждень (простий графік, 5 точок)
- Активні цілі (прогрес)

**3. Налаштування**
- Час брифінгів (ранок/вечір)
- Тиха година (не турбувати з ... до ...)
- Резервний PIN
- Експорт даних (розшифрований JSON)
- Видалити всі дані

### Дизайн

- Темна тема за замовчуванням (менше навантаження на очі ввечері)
- Мінімалістичний: без яскравих кольорів, спокійні тони
- Шрифт: системний (швидкість завантаження)
- Анімації: тільки при відправці повідомлення і отриманні відповіді
- Без логотипів, без брендингу — це твій приватний простір

---

## Service Worker (sw.js)

```javascript
// Кешування для офлайн-роботи
const CACHE = 'myday-v1';
const ASSETS = ['/', '/index.html', '/manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)));
});

self.addEventListener('fetch', e => {
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request))
  );
});

// Push-нотифікації
self.addEventListener('push', e => {
  const data = e.data?.json() || {};
  e.waitUntil(
    self.registration.showNotification(data.title || 'Мій день', {
      body: data.body || 'Нове нагадування',
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
      tag: data.tag || 'default',
      data: { url: '/' }
    })
  );
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(clients.openWindow(e.notification.data.url));
});
```

---

## manifest.json

```json
{
  "name": "Мій день",
  "short_name": "Мій день",
  "description": "Персональний AI-помічник",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#1a1a1a",
  "theme_color": "#1a1a1a",
  "orientation": "portrait",
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

---

## Railway: змінні середовища

```
ANTHROPIC_API_KEY=sk-ant-...
FIREBASE_API_KEY=...                    (окремий від FlashSmart)
FIREBASE_DB_URL=https://sklad-oblik-default-rtdb.europe-west1.firebasedatabase.app
FIREBASE_EMAIL=myday@flashsmart.local   (окремий сервісний акаунт)
FIREBASE_PASSWORD=...
JWT_SECRET=...                          (для токенів авторизації)
FCM_SERVER_KEY=...                      (для push-нотифікацій)
ENCRYPTION_TRANSIT_KEY=...              (для тимчасового розшифрування на сервері)
```

---

## Firebase Security Rules (доповнення)

```json
{
  "rules": {
    "sklad": { "...": "існуючі правила" },

    "myday": {
      "user": {
        ".read": "auth.uid === 'MYDAY_SERVICE_UID'",
        ".write": "auth.uid === 'MYDAY_SERVICE_UID'"
      },
      "facts": {
        ".read": "auth.uid === 'MYDAY_SERVICE_UID'",
        ".write": "auth.uid === 'MYDAY_SERVICE_UID'",
        ".indexOn": ["category", "created"]
      },
      "events": {
        ".read": "auth.uid === 'MYDAY_SERVICE_UID'",
        ".write": "auth.uid === 'MYDAY_SERVICE_UID'",
        ".indexOn": ["date", "done"]
      },
      "journal": {
        ".read": "auth.uid === 'MYDAY_SERVICE_UID'",
        ".write": "auth.uid === 'MYDAY_SERVICE_UID'"
      },
      "goals": {
        ".read": "auth.uid === 'MYDAY_SERVICE_UID'",
        ".write": "auth.uid === 'MYDAY_SERVICE_UID'",
        ".indexOn": ["active"]
      }
    }
  }
}
```

---

## Етапи розробки

### Етап 1 — Фундамент (1 тиждень)
- [ ] Створити репозиторій `my-day-app` на GitHub
- [ ] Створити `index.html` з PWA-оболонкою (manifest, SW, базовий UI)
- [ ] Створити репозиторій `my-day-bot` на GitHub
- [ ] Налаштувати FastAPI на Railway
- [ ] Створити Firebase Auth акаунт `myday@flashsmart.local`
- [ ] Додати Security Rules для `/myday`
- [ ] Реалізувати Passkey реєстрацію і вхід
- [ ] Реалізувати шифрування (Web Crypto на клієнті)

### Етап 2 — Чат і AI (1 тиждень)
- [ ] Ендпоінт POST /message
- [ ] Claude промпт для парсингу намірів (факт / подія / журнал / ціль / розмова)
- [ ] Збереження розпарсених даних у Firebase (зашифровано)
- [ ] Чат-інтерфейс у PWA
- [ ] Історія повідомлень (локальне збереження)

### Етап 3 — Нагадування, push, погода і свята (1 тиждень)
- [ ] Firebase Cloud Messaging — інтеграція
- [ ] Service Worker — обробка push
- [ ] Cron: перевірка нагадувань кожні 30 хв
- [ ] Ранковий брифінг (07:30)
- [ ] Вечірній звіт (21:00)
- [ ] weather_service.py — Open-Meteo API (погода + схід/захід)
- [ ] holidays.py + holidays_data.json — українські свята та іменини
- [ ] Інтеграція погоди і свят у ранковий брифінг

### Етап 4 — Дашборд і патерни (1 тиждень)
- [ ] Екран дашборду: події дня, нагадування
- [ ] Графік настрою за тиждень
- [ ] Цілі з прогресом
- [ ] Тижневий огляд (неділя 10:00)
- [ ] Детектор патернів (сон, настрій)

### Етап 5 — Полірування (3-5 днів)
- [ ] Офлайн-режим (кешовані дані)
- [ ] Експорт даних
- [ ] Видалення акаунту
- [ ] Тестування на iPhone і Android
- [ ] Оптимізація швидкості

---

## Погода (Open-Meteo API)

Безкоштовний API, без ключа, без реєстрації, без лімітів для персонального використання.

```python
# weather_service.py
import httpx
from datetime import datetime

# Координати міста з профілю користувача
CITIES = {
    "Львів": {"lat": 49.84, "lon": 24.03},
    "Київ": {"lat": 50.45, "lon": 30.52},
    # додаються при реєстрації
}

async def get_weather(city: str) -> dict:
    coords = CITIES.get(city, CITIES["Київ"])
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": coords["lat"],
        "longitude": coords["lon"],
        "current": "temperature_2m,apparent_temperature,rain,wind_speed_10m,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset,weather_code",
        "timezone": "Europe/Kyiv",
        "forecast_days": 2  # сьогодні + завтра
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)
        data = r.json()

    current = data["current"]
    today = data["daily"]

    return {
        "temp": round(current["temperature_2m"]),
        "feels_like": round(current["apparent_temperature"]),
        "rain": current["rain"] > 0,
        "wind": round(current["wind_speed_10m"]),
        "high": round(today["temperature_2m_max"][0]),
        "low": round(today["temperature_2m_min"][0]),
        "rain_chance": today["precipitation_probability_max"][0],
        "sunrise": today["sunrise"][0][-5:],      # "06:23"
        "sunset": today["sunset"][0][-5:],         # "20:41"
        "tomorrow_high": round(today["temperature_2m_max"][1]),
        "tomorrow_low": round(today["temperature_2m_min"][1]),
        "tomorrow_rain": today["precipitation_probability_max"][1],
    }

# Приклад використання в брифінгу:
# weather = await get_weather("Львів")
# → {"temp": 22, "feels_like": 20, "rain": False, "wind": 12,
#    "high": 25, "low": 14, "rain_chance": 15,
#    "sunrise": "05:23", "sunset": "20:41",
#    "tomorrow_high": 19, "tomorrow_low": 11, "tomorrow_rain": 80}
```

### Що потрапляє в брифінг

Ранковий (07:30): "Зараз 18°, вдень до 25°. Дощу не очікується. Сонце зайде о 20:41."
Або: "Зараз 14°, вдень до 17°. Дощ 80% — візьми парасольку. Сонце зайде о 20:38."

Вечірній (21:00): "Завтра до 19°, дощ ймовірний (80%). Схід о 05:21."

### Розумні підказки (Claude генерує на основі погоди + контексту)

- rain_chance > 60% → "Візьми парасольку"
- temp < 5° → "Одягнись тепліше"
- Є подія "тренування на вулиці" + дощ → "Сьогодні дощ — можливо, краще зал?"
- sunset рано + дитина на вулиці → "Темніє о 17:30, дитина ще гуляє?"

---

## Свята та іменини

Вбудований JSON-файл, без API. Оновлюється вручну раз на рік (або ніколи — свята не змінюються).

```python
# holidays.py
import json
from datetime import date

with open("holidays_data.json", "r", encoding="utf-8") as f:
    HOLIDAYS_DB = json.load(f)

def get_today_holidays(today: date = None) -> dict:
    today = today or date.today()
    key = today.strftime("%m-%d")  # "05-20"

    result = {
        "state": [],      # державні свята
        "notable": [],    # пам'ятні дати
        "namedays": [],   # іменини
    }

    if key in HOLIDAYS_DB.get("state", {}):
        result["state"] = HOLIDAYS_DB["state"][key]
    if key in HOLIDAYS_DB.get("notable", {}):
        result["notable"] = HOLIDAYS_DB["notable"][key]
    if key in HOLIDAYS_DB.get("namedays", {}):
        result["namedays"] = HOLIDAYS_DB["namedays"][key]

    return result

# Приклад:
# get_today_holidays(date(2026, 5, 20))
# → {"state": [], "notable": ["День вишиванки"],
#    "namedays": ["Михайло", "Степан"]}
```

### holidays_data.json (фрагмент)

```json
{
  "state": {
    "01-01": ["Новий рік"],
    "01-07": ["Різдво Христове"],
    "03-08": ["Міжнародний жіночий день"],
    "05-01": ["День праці"],
    "05-09": ["День Європи"],
    "06-28": ["День Конституції"],
    "08-24": ["День Незалежності"],
    "10-01": ["День захисників і захисниць"],
    "10-14": ["День захисника України"],
    "12-25": ["Різдво (за григоріанським календарем)"]
  },
  "notable": {
    "01-22": ["День Соборності"],
    "02-14": ["День закоханих"],
    "02-20": ["День Героїв Небесної Сотні"],
    "05-20": ["День вишиванки"],
    "06-01": ["День захисту дітей"],
    "11-21": ["День Гідності та Свободи"]
  },
  "namedays": {
    "01-01": ["Іван", "Василь"],
    "01-14": ["Василь", "Маланка"],
    "05-20": ["Михайло", "Степан"],
    "07-07": ["Іван"]
  },
  "family_dates": {}
}
```

### Ключова фіча: сімейні дати

Коли користувач додає факт "день народження мами 15 березня", система зберігає його і в `/facts`, і в `holidays_data` (в пам'яті) під ключем `family_dates`:

```json
"family_dates": {
  "03-15": ["День народження мами"],
  "09-01": ["Перший день школи"],
  "11-22": ["Річниця весілля"]
}
```

Ці дати потрапляють у ранковий брифінг нарівні зі святами: "Сьогодні день народження мами — не забудь привітати!"

---

```python
SYSTEM_PROMPT = """Ти — парсер повідомлень для персонального помічника "Мій день".

Користувач пише тобі вільним текстом українською. Твоє завдання:
1. Визначити тип наміру
2. Витягти структуровані дані
3. Згенерувати коротку відповідь

Типи намірів:
- EVENT: нагадування, подія з датою/часом
- FACT: постійний факт (алергія, день народження, школа дитини)
- JOURNAL: запис про стан (здоров'я, настрій, сон, що сталося)
- GOAL: ціль або звичка (почати бігати, читати щодня)
- CHAT: просто розмова, не потребує збереження

Відповідай ТІЛЬКИ валідним JSON:

{
  "type": "EVENT|FACT|JOURNAL|GOAL|CHAT",
  "data": {
    // для EVENT:
    "text": "забрати дитину",
    "date": "2026-05-22",
    "time": "14:00",
    "repeat": null,           // "daily", "weekly", "monthly" або null
    "remind_before_min": 30   // за скільки хвилин нагадати

    // для FACT:
    "text": "алергія на амброзію",
    "category": "health",     // family, health, home, other

    // для JOURNAL:
    "text": "погано спав, болить голова",
    "mood": 2,                // 1-5 (1=погано, 5=чудово)
    "tags": ["sleep", "health"]

    // для GOAL:
    "text": "бігати вранці 3 рази на тиждень",
    "frequency": "3/week"

    // для CHAT:
    "text": null
  },
  "response": "Записав. Нагадаю завтра о 13:30."
}

Правила відповіді:
- Українською, природно, без канцеляризмів
- Коротко: 1-2 речення максимум
- Не питай зайвого, якщо зрозуміло
- Якщо дата не вказана, але зрозуміла з контексту ("завтра", "в суботу") — вирахуй
- Сьогодні: {current_date}, день тижня: {weekday}
- Погода: {weather_summary}
- Свята сьогодні: {holidays_today}
- Сімейні дати сьогодні: {family_dates_today}
"""
```

---

## Безпека: підсумок

| Загроза | Захист |
|---|---|
| Зламали Firebase | Дані зашифровані AES-256-GCM, без ключа — сміття |
| Зламали сервер (Railway) | Дані в пам'яті тільки під час запиту, не логуються |
| Зламали GitHub (код) | Код публічний, секретів немає, ключі в Railway env |
| Вкрали телефон | Passkey вимагає біометрію, без пальця/обличчя — нікуди |
| Шкідливе розширення браузера | Ключ у Secure Enclave, JS не може його прочитати |
| Перехоплення трафіку | HTTPS + дані зашифровані ще до відправки |
| Забув PIN | Дані втрачені назавжди (це фіча, не баг) |

---

## Що НЕ входить у v1

- Голосовий ввід (потребує Speech API, складно)
- Розпізнавання фото (рецепти, документи)
- Інтеграція з Google Calendar (потребує OAuth)
- Мультикористувацький режим (сім'я)
- Telegram-міст (пересилання з Telegram у помічник)
- RSS-стрічки новин (потребує налаштування)

Все це — кандидати на v2 після того, як v1 стабільно працює 2-3 тижні.

---

## Що ВХОДИТЬ у v1 (підсумок)

| Функція | Джерело даних | Приватність |
|---|---|---|
| Чат з AI-помічником | Ти пишеш → Claude парсить | Зашифровано |
| Факти (сім'я, здоров'я) | Ти пишеш | Зашифровано |
| Події і нагадування | Ти пишеш | Зашифровано |
| Журнал (настрій, сон) | Ти пишеш | Зашифровано |
| Цілі і звички | Ти пишеш | Зашифровано |
| Погода і прогноз | Open-Meteo API | Публічні дані, без акаунту |
| Схід/захід сонця | Open-Meteo API | Публічні дані |
| Свята та іменини | Вбудований JSON | Локальний файл |
| Сімейні дати | Витягуються з фактів | Зашифровано |
| Push-нотифікації | Firebase FCM | Тільки заголовок, без деталей |
| Passkey-автентифікація | Secure Enclave | Ключ у чипі |

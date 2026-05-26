"""
AI-движок: парсинг намірів і генерація брифінгів через Claude API.
"""
import os
import json
import logging
from datetime import datetime

import anthropic

log = logging.getLogger("myday.ai")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-20250514"

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ──────────────────────────────────────────────
#  Intent parsing
# ──────────────────────────────────────────────

INTENT_SYSTEM = """Ти — парсер повідомлень для персонального помічника "Мій день".

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

Відповідай ТІЛЬКИ валідним JSON без Markdown-обгортки:

{
  "type": "EVENT|FACT|JOURNAL|GOAL|CHAT",
  "data": {
    "text": "...",

    // додатково для EVENT:
    "date": "2026-05-22",
    "time": "14:00",
    "repeat": null,
    "remind_before_min": 30,

    // додатково для FACT:
    "category": "family|health|home|other",

    // додатково для JOURNAL:
    "mood": 3,
    "tags": ["sleep", "health"],

    // додатково для GOAL:
    "frequency": "3/week"
  },
  "response": "Записав. Нагадаю завтра о 13:30."
}

Правила:
- Українською, природно, без канцеляризмів і русизмів
- Коротко: 1-2 речення максимум
- Не питай зайвого, якщо зрозуміло
- Якщо дата не вказана, але зрозуміла з контексту ("завтра", "в суботу") — вирахуй
- Якщо тип CHAT — data.text = null, response = твоя відповідь на розмову
- Ніколи не вигадуй дати чи факти, яких немає в повідомленні
- Звертайся на "ти" (неформально, як друг)
- На запитання про погоду (зараз, завтра, на тиждень, на конкретний день) використовуй дані з контексту "Прогноз на 7 днів" і давай конкретну відповідь
- Не кажи "не маю даних" якщо інформація є в контексті"""


async def parse_intent(
    message: str,
    weather: dict = None,
    holidays: dict = None,
    known_facts: list[str] = None,
) -> dict:
    """Parse user message into structured intent using Claude."""
    now = datetime.now()
    weekdays_uk = ["понеділок", "вівторок", "середа", "четвер", "п'ятниця", "субота", "неділя"]

    context_parts = [
        f"Сьогодні: {now.strftime('%Y-%m-%d')}, {weekdays_uk[now.weekday()]}",
    ]

    if weather:
        w = weather
        context_parts.append(
            f"Погода зараз: {w.get('temp', '?')}°C, відчувається як {w.get('feels_like', '?')}°C, "
            f"{w.get('description', '')}, вітер {w.get('wind', '?')} км/год, дощ {w.get('rain_chance', '?')}%, "
            f"схід {w.get('sunrise', '?')}, захід {w.get('sunset', '?')}"
        )
        forecast = w.get("forecast", [])
        if forecast:
            forecast_lines = ["Прогноз на 7 днів:"]
            for f in forecast:
                forecast_lines.append(
                    f"  {f.get('label', '?')} ({f.get('date', '?')}): "
                    f"{f.get('low', '?')}…{f.get('high', '?')}°C, "
                    f"дощ {f.get('rain_chance', 0)}%, {f.get('description', '')}"
                )
            context_parts.append("\n".join(forecast_lines))

    if holidays:
        all_holidays = holidays.get("state", []) + holidays.get("notable", []) + holidays.get("family_dates", [])
        if all_holidays:
            context_parts.append(f"Свята сьогодні: {', '.join(all_holidays)}")
        namedays = holidays.get("namedays", [])
        if namedays:
            context_parts.append(f"Іменини: {', '.join(namedays)}")

    if known_facts:
        context_parts.append(f"Відомі факти про користувача:\n" + "\n".join(f"- {f}" for f in known_facts[:10]))

    context = "\n".join(context_parts)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=INTENT_SYSTEM,
            messages=[
                {"role": "user", "content": f"Контекст:\n{context}\n\nПовідомлення: {message}"}
            ],
        )

        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        result = json.loads(text)

        # Validate required fields
        if "type" not in result or "response" not in result:
            raise ValueError("Missing type or response")

        if "data" not in result:
            result["data"] = {"text": None}

        return result

    except (json.JSONDecodeError, ValueError, KeyError) as e:
        log.error("Intent parse failed: %s — raw: %s", e, text if 'text' in dir() else "no response")
        return {
            "type": "CHAT",
            "data": {"text": None},
            "response": "Вибач, не зрозумів. Спробуй сказати інакше.",
        }
    except Exception as e:
        log.error("Claude API error: %s", e)
        return {
            "type": "CHAT",
            "data": {"text": None},
            "response": "Щось пішло не так. Спробуй ще раз через хвилину.",
        }


# ──────────────────────────────────────────────
#  Briefing generation
# ──────────────────────────────────────────────

BRIEFING_SYSTEM = """Ти — персональний помічник "Мій день". Тобі потрібно скласти короткий брифінг.

Правила:
- Українською, тепло і природно, без канцеляризмів
- Починай з привітання відповідно до часу доби:
  * 5:00-11:59 → "Доброго ранку"
  * 12:00-17:59 → "Доброго дня"
  * 18:00-22:59 → "Добрий вечір"
  * 23:00-4:59 → "Доброї ночі"
- Погода: коротко, з практичною порадою (парасолька, одягнутися тепліше)
- Свята: згадай, якщо є
- Події дня: перелічи, якщо є, з часом
- Настрій: якщо є патерн (3+ дні поганий настрій) — м'яко зверни увагу
- Цілі: нагадай про активні, без тиску
- Загальна довжина: 3-6 речень, не більше
- Звертайся на "ти" (як друг)
- Не вигадуй події чи факти, яких немає в даних"""


async def generate_briefing(
    weather: dict = None,
    holidays: dict = None,
    events: list = None,
    moods: list = None,
    goals: list = None,
) -> str:
    """Generate briefing text based on time of day."""
    now = datetime.now()
    hour = now.hour

    if 5 <= hour < 12:
        time_label = "ранок"
    elif 12 <= hour < 18:
        time_label = "день"
    elif 18 <= hour < 23:
        time_label = "вечір"
    else:
        time_label = "ніч"

    is_morning = hour < 14

    data_parts = [
        f"Поточний час: {now.strftime('%H:%M')} ({time_label})",
    ]

    if weather:
        w = weather
        data_parts.append(
            f"Погода: зараз {w.get('temp', '?')}°C, вдень до {w.get('high', '?')}°C, "
            f"дощ {w.get('rain_chance', '?')}%, вітер {w.get('wind', '?')} км/год, "
            f"схід {w.get('sunrise', '?')}, захід {w.get('sunset', '?')}"
        )
        if not is_morning:
            data_parts.append(
                f"Завтра: {w.get('tomorrow_high', '?')}°C / {w.get('tomorrow_low', '?')}°C, "
                f"дощ {w.get('tomorrow_rain', '?')}%"
            )

    if holidays:
        all_h = holidays.get("state", []) + holidays.get("notable", []) + holidays.get("family_dates", [])
        if all_h:
            data_parts.append(f"Свята: {', '.join(all_h)}")
        names = holidays.get("namedays", [])
        if names:
            data_parts.append(f"Іменини: {', '.join(names)}")

    if events:
        data_parts.append("Події сьогодні:")
        for ev in events:
            t = ev.get("time", "")
            txt = ev.get("text", "?")
            data_parts.append(f"  - {t + ' ' if t else ''}{txt}")
    else:
        data_parts.append("Подій на сьогодні немає.")

    if moods:
        mood_str = ", ".join(f"{m['date']}: {m['mood']}/5" for m in moods)
        data_parts.append(f"Настрій за останні дні: {mood_str}")

    if goals:
        data_parts.append("Активні цілі:")
        for g in goals[:5]:
            data_parts.append(f"  - {g.get('text', '?')}")

    data_text = "\n".join(data_parts)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=300,
            system=BRIEFING_SYSTEM,
            messages=[
                {"role": "user", "content": f"Дані для брифінгу:\n{data_text}"}
            ],
        )
        return response.content[0].text.strip()

    except Exception as e:
        log.error("Briefing generation failed: %s", e)
        # Fallback: simple text
        parts = []
        if is_morning:
            parts.append("Доброго ранку!")
        else:
            parts.append("Добрий вечір!")

        if weather:
            parts.append(f"Зараз {weather.get('temp', '?')}°C.")

        if events:
            parts.append(f"Сьогодні {len(events)} подій.")

        return " ".join(parts)

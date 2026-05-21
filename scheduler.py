"""
Планувальник: ранкові/вечірні брифінги, перевірка нагадувань.
Використовує APScheduler.
"""
import os
import json
import time
import logging
import asyncio
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from push_service import send_push

log = logging.getLogger("myday.scheduler")


def start_scheduler():
    """Initialize and start the background scheduler."""
    scheduler = BackgroundScheduler(timezone="Europe/Kyiv")

    # Morning briefing at 07:30
    scheduler.add_job(
        _run_async_job, "cron",
        args=[_morning_briefing],
        hour=7, minute=30,
        id="morning_briefing",
    )

    # Evening report at 21:00
    scheduler.add_job(
        _run_async_job, "cron",
        args=[_evening_report],
        hour=21, minute=0,
        id="evening_report",
    )

    # Check reminders every 30 minutes
    scheduler.add_job(
        _run_async_job, "cron",
        args=[_check_reminders],
        minute="*/30",
        id="check_reminders",
    )

    # Weekly review on Sunday at 10:00
    scheduler.add_job(
        _run_async_job, "cron",
        args=[_weekly_review],
        day_of_week="sun", hour=10, minute=0,
        id="weekly_review",
    )

    # Weather cache refresh at 06:00
    scheduler.add_job(
        _run_async_job, "cron",
        args=[_refresh_weather],
        hour=6, minute=0,
        id="refresh_weather",
    )

    scheduler.start()
    log.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))


def _run_async_job(coro_func):
    """Run async function from sync scheduler context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(coro_func())
        else:
            loop.run_until_complete(coro_func())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(coro_func())


async def _morning_briefing():
    """Generate and send morning briefing."""
    log.info("Generating morning briefing...")
    try:
        # Import here to avoid circular imports
        from main import fb_get
        from ai_engine import generate_briefing
        from weather_service import get_weather
        from holidays import get_today_holidays
        from crypto_utils import decrypt_data

        settings = await fb_get("user/settings") or {}
        city = settings.get("city", "Київ")

        # Check quiet hours
        quiet_start = settings.get("quiet_start")
        quiet_end = settings.get("quiet_end")
        if _is_quiet_hour(quiet_start, quiet_end):
            log.info("Quiet hour — skipping morning briefing")
            return

        weather = await get_weather(city)
        holidays = get_today_holidays()

        # Get today's events
        today = datetime.now().strftime("%Y-%m-%d")
        events = await fb_get("events") or {}
        enc_key = os.environ.get("ENCRYPTION_TRANSIT_KEY", "")
        today_events = []
        for eid, edata in (events.items() if isinstance(events, dict) else []):
            if edata.get("date") == today and not edata.get("done"):
                try:
                    decrypted = decrypt_data(edata.get("data", ""), enc_key)
                    today_events.append(json.loads(decrypted))
                except Exception:
                    pass

        # Get recent moods
        journal = await fb_get("journal") or {}
        recent_moods = []
        for jkey in sorted(journal.keys() if isinstance(journal, dict) else [], reverse=True)[:7]:
            jdata = journal[jkey]
            if isinstance(jdata, dict) and "mood" in jdata:
                recent_moods.append({"date": jkey, "mood": jdata["mood"]})

        # Get active goals
        goals = await fb_get("goals") or {}
        active_goals = []
        for gid, gdata in (goals.items() if isinstance(goals, dict) else []):
            if gdata.get("active"):
                try:
                    decrypted = decrypt_data(gdata.get("data", ""), enc_key)
                    active_goals.append(json.loads(decrypted))
                except Exception:
                    pass

        briefing = await generate_briefing(
            weather=weather,
            holidays=holidays,
            events=today_events,
            moods=recent_moods,
            goals=active_goals,
        )

        # Send push (only title + generic body, no sensitive data in push payload)
        await send_push(
            title="Доброго ранку ☀️",
            body="Брифінг на сьогодні готовий",
            tag="morning_briefing",
        )

        log.info("Morning briefing sent")

    except Exception as e:
        log.error("Morning briefing failed: %s", e)


async def _evening_report():
    """Generate and send evening report."""
    log.info("Generating evening report...")
    try:
        await send_push(
            title="Добрий вечір 🌙",
            body="Вечірнє зведення готове",
            tag="evening_report",
        )
        log.info("Evening report sent")
    except Exception as e:
        log.error("Evening report failed: %s", e)


async def _check_reminders():
    """Check for upcoming reminders in next 30 minutes."""
    try:
        from main import fb_get
        from crypto_utils import decrypt_data

        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        current_time = now.strftime("%H:%M")

        events = await fb_get("events") or {}
        enc_key = os.environ.get("ENCRYPTION_TRANSIT_KEY", "")

        for eid, edata in (events.items() if isinstance(events, dict) else []):
            if edata.get("date") != today or edata.get("done"):
                continue

            try:
                decrypted = json.loads(decrypt_data(edata.get("data", ""), enc_key))
                event_time = decrypted.get("time", "")
                remind_before = decrypted.get("remind_before_min", 30)

                if event_time:
                    eh, em = map(int, event_time.split(":"))
                    nh, nm = now.hour, now.minute
                    diff_min = (eh * 60 + em) - (nh * 60 + nm)

                    if 0 < diff_min <= remind_before:
                        await send_push(
                            title="Нагадування",
                            body=f"Через {diff_min} хв",
                            tag=f"reminder_{eid}",
                        )
            except Exception:
                pass

    except Exception as e:
        log.error("Reminder check failed: %s", e)


async def _weekly_review():
    """Send weekly review push."""
    log.info("Sending weekly review...")
    try:
        await send_push(
            title="Тижневий огляд 📊",
            body="Підсумки тижня готові",
            tag="weekly_review",
        )
    except Exception as e:
        log.error("Weekly review failed: %s", e)


async def _refresh_weather():
    """Pre-fetch weather for cache."""
    try:
        from main import fb_get
        from weather_service import get_weather

        settings = await fb_get("user/settings") or {}
        city = settings.get("city", "Київ")
        await get_weather(city)
        log.info("Weather cache refreshed for %s", city)
    except Exception as e:
        log.error("Weather refresh failed: %s", e)


def _is_quiet_hour(quiet_start: str | None, quiet_end: str | None) -> bool:
    """Check if current time is within quiet hours."""
    if not quiet_start or not quiet_end:
        return False

    try:
        now = datetime.now().strftime("%H:%M")
        if quiet_start <= quiet_end:
            return quiet_start <= now <= quiet_end
        else:  # crosses midnight
            return now >= quiet_start or now <= quiet_end
    except Exception:
        return False

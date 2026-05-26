"""
Планувальник: ранкові/вечірні брифінги, перевірка нагадувань.
Використовує APScheduler AsyncIOScheduler.
"""
import os
import json
import time
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from push_service import send_push

log = logging.getLogger("myday.scheduler")

_scheduler = None


def start_scheduler():
    """Initialize and start the async scheduler. Call from inside running event loop."""
    global _scheduler
    if _scheduler is not None:
        log.info("Scheduler already started")
        return

    _scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")

    # Morning briefing at 07:30
    _scheduler.add_job(
        _morning_briefing, "cron",
        hour=7, minute=30,
        id="morning_briefing",
    )

    # Evening report at 21:00
    _scheduler.add_job(
        _evening_report, "cron",
        hour=21, minute=0,
        id="evening_report",
    )

    # Check reminders every 5 minutes (was 30 — too rare for accurate reminders)
    _scheduler.add_job(
        _check_reminders, "cron",
        minute="*/5",
        id="check_reminders",
    )

    # Weekly review on Sunday at 10:00
    _scheduler.add_job(
        _weekly_review, "cron",
        day_of_week="sun", hour=10, minute=0,
        id="weekly_review",
    )

    # Weather cache refresh at 06:00
    _scheduler.add_job(
        _refresh_weather, "cron",
        hour=6, minute=0,
        id="refresh_weather",
    )

    _scheduler.start()
    log.info("AsyncIOScheduler started with %d jobs", len(_scheduler.get_jobs()))
    for job in _scheduler.get_jobs():
        log.info("  Job: %s, next run: %s", job.id, job.next_run_time)


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

        # Send the actual briefing as push + save to chat
        await send_push(
            title="Мій день — ранковий брифінг",
            body=briefing,
            tag="morning_briefing",
            save_to_chat=True,
        )

        log.info("Morning briefing sent: %s", briefing[:80])

    except Exception as e:
        log.error("Morning briefing failed: %s", e)


async def _evening_report():
    """Generate and send evening report."""
    log.info("Generating evening report...")
    try:
        from main import fb_get
        from ai_engine import generate_briefing
        from weather_service import get_weather
        from holidays import get_today_holidays
        from crypto_utils import decrypt_data

        settings = await fb_get("user/settings") or {}
        city = settings.get("city", "Київ")

        quiet_start = settings.get("quiet_start")
        quiet_end = settings.get("quiet_end")
        if _is_quiet_hour(quiet_start, quiet_end):
            log.info("Quiet hour — skipping evening report")
            return

        weather = await get_weather(city)
        holidays = get_today_holidays()

        today = datetime.now().strftime("%Y-%m-%d")
        events = await fb_get("events") or {}
        enc_key = os.environ.get("ENCRYPTION_TRANSIT_KEY", "")
        today_events = []
        for eid, edata in (events.items() if isinstance(events, dict) else []):
            if edata.get("date") == today:
                try:
                    decrypted = decrypt_data(edata.get("data", ""), enc_key)
                    today_events.append(json.loads(decrypted))
                except Exception:
                    pass

        journal = await fb_get("journal") or {}
        recent_moods = []
        for jkey in sorted(journal.keys() if isinstance(journal, dict) else [], reverse=True)[:7]:
            jdata = journal[jkey]
            if isinstance(jdata, dict) and "mood" in jdata:
                recent_moods.append({"date": jkey, "mood": jdata["mood"]})

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

        await send_push(
            title="Мій день — вечірній звіт",
            body=briefing,
            tag="evening_report",
            save_to_chat=True,
        )

        log.info("Evening report sent")
    except Exception as e:
        log.error("Evening report failed: %s", e)


async def _check_reminders():
    """Check events that need reminding within next 5 minutes."""
    try:
        from main import fb_get, fb_patch
        from crypto_utils import decrypt_data

        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        events = await fb_get("events") or {}
        enc_key = os.environ.get("ENCRYPTION_TRANSIT_KEY", "")

        if not isinstance(events, dict):
            return

        sent_count = 0
        for eid, edata in events.items():
            if not isinstance(edata, dict):
                continue
            if edata.get("date") != today or edata.get("done"):
                continue
            if edata.get("reminded"):
                continue  # already reminded

            try:
                decrypted = json.loads(decrypt_data(edata.get("data", ""), enc_key))
                event_time = decrypted.get("time", "")
                event_text = decrypted.get("text", "подія")
                remind_before = decrypted.get("remind_before_min", 30)

                if not event_time:
                    continue

                eh, em = map(int, event_time.split(":"))
                nh, nm = now.hour, now.minute
                diff_min = (eh * 60 + em) - (nh * 60 + nm)

                # Send reminder if we're in the window: just entered the remind_before zone
                # i.e., diff_min is between (remind_before - 5) and remind_before
                # This way we send only once per event
                if (remind_before - 5) < diff_min <= remind_before:
                    log.info("Sending reminder for event %s: %s in %d min", eid, event_text, diff_min)
                    await send_push(
                        title="Нагадування",
                        body=f"{event_text} — через {diff_min} хв (о {event_time})",
                        tag=f"reminder_{eid}",
                    )
                    # Mark as reminded so we don't send again
                    await fb_patch(f"events/{eid}", {"reminded": True})
                    sent_count += 1

            except Exception as e:
                log.warning("Failed to process event %s: %s", eid, e)

        if sent_count == 0:
            log.debug("Reminder check: no events to remind")

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

"""
Push-нотифікації через Web Push (VAPID).
Працює з PWA на iOS 16.4+ та Android.
Надсилає тільки заголовок і загальний текст — жодних персональних даних у push.
"""
import os
import json
import logging

from pywebpush import webpush, WebPushException

log = logging.getLogger("myday.push")

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_EMAIL = os.environ.get("VAPID_EMAIL", "mailto:admin@example.com")


async def send_push(title: str, body: str, tag: str = "default") -> bool:
    """
    Send Web Push notification to the registered device.
    IMPORTANT: Never include personal data in push payload.
    """
    if not VAPID_PRIVATE_KEY:
        log.warning("VAPID_PRIVATE_KEY not set, skipping push")
        return False

    # Get subscription from Firebase
    try:
        from main import fb_get
        sub_data = await fb_get("user/push_subscription")
        if not sub_data or not sub_data.get("subscription"):
            log.warning("No push subscription registered")
            return False

        subscription = json.loads(sub_data["subscription"])
    except Exception as e:
        log.error("Failed to get subscription: %s", e)
        return False

    payload = json.dumps({
        "title": title,
        "body": body,
        "tag": tag,
    }, ensure_ascii=False)

    try:
        webpush(
            subscription_info=subscription,
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_EMAIL},
        )
        log.info("Push sent: %s", title)
        return True
    except WebPushException as e:
        log.error("Web push failed: %s", e)
        # If 410 Gone — subscription expired, remove from DB
        if e.response and e.response.status_code in (404, 410):
            log.info("Subscription expired, removing")
            try:
                from main import fb_put
                await fb_put("user/push_subscription", None)
            except Exception:
                pass
        return False
    except Exception as e:
        log.error("Push send error: %s", e)
        return False

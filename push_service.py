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


async def send_push(title: str, body: str, tag: str = "default", save_to_chat: bool = True) -> bool:
    """
    Send Web Push notification to the registered device.
    Optionally saves the notification as a bot message in chat history.
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

    push_sent = False
    try:
        webpush(
            subscription_info=subscription,
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_EMAIL},
        )
        log.info("Push sent: %s", title)
        push_sent = True
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
    except Exception as e:
        log.error("Push send error: %s", e)

    # Save to chat history so user can see notification in chat (even if push failed or missed)
    if save_to_chat:
        try:
            from main import fb_post, encrypt_data, ENCRYPTION_KEY
            import time as _time
            chat_payload = {
                "user": "",
                "bot": body,
                "type": "NOTIFICATION",
            }
            encrypted_chat = encrypt_data(json.dumps(chat_payload, ensure_ascii=False), ENCRYPTION_KEY)
            await fb_post("chat", {
                "data": encrypted_chat,
                "created": int(_time.time() * 1000),
            })
        except Exception as e:
            log.warning("Failed to save push to chat: %s", e)

    return push_sent

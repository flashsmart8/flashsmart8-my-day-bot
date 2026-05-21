"""
Push-нотифікації через Firebase Cloud Messaging (FCM).
Надсилає тільки заголовок і загальний текст — жодних персональних даних у push.
"""
import os
import logging

import httpx

log = logging.getLogger("myday.push")

FCM_SERVER_KEY = os.environ.get("FCM_SERVER_KEY", "")
FIREBASE_DB_URL = os.environ.get("FIREBASE_DB_URL", "")


async def send_push(title: str, body: str, tag: str = "default") -> bool:
    """
    Send push notification to the registered device.
    IMPORTANT: Never include personal data in push payload.
    Push is visible on lock screen — only generic titles/body.
    """
    if not FCM_SERVER_KEY:
        log.warning("FCM_SERVER_KEY not set, skipping push")
        return False

    # Get FCM token from Firebase
    try:
        from main import fb_get
        token_data = await fb_get("user/fcm_token")
        if not token_data or not token_data.get("token"):
            log.warning("No FCM token registered, skipping push")
            return False

        fcm_token = token_data["token"]
    except Exception as e:
        log.error("Failed to get FCM token: %s", e)
        return False

    # Send via FCM HTTP v1 (legacy API for simplicity)
    url = "https://fcm.googleapis.com/fcm/send"
    headers = {
        "Authorization": f"key={FCM_SERVER_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": fcm_token,
        "notification": {
            "title": title,
            "body": body,
            "tag": tag,
            "icon": "/icons/icon-192.png",
        },
        "data": {
            "tag": tag,
            "url": "/",
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers=headers, timeout=10)
            if r.status_code == 200:
                result = r.json()
                if result.get("success", 0) > 0:
                    log.info("Push sent: %s", title)
                    return True
                else:
                    log.warning("Push failed: %s", result)
                    return False
            else:
                log.error("FCM request failed: %s %s", r.status_code, r.text)
                return False
    except Exception as e:
        log.error("Push send error: %s", e)
        return False

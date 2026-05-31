import json
import os
import urllib.error
import urllib.request
from datetime import datetime

DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]


def _format_time(state_change_time: str) -> str:
    try:
        dt = datetime.strptime(state_change_time[:19], "%Y-%m-%dT%H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return state_change_time


def lambda_handler(event, context):
    for record in event["Records"]:
        sns_message = json.loads(record["Sns"]["Message"])

        alarm_name = sns_message.get("AlarmName", "Unknown")
        state_change_time = sns_message.get("StateChangeTime", "")
        new_state_reason = sns_message.get("NewStateReason", "Unknown")

        message = (
            f"[GREŠKA] {alarm_name}\n"
            f"Vreme: {_format_time(state_change_time)}\n"
            f"Razlog: {new_state_reason}"
        )

        payload = json.dumps({"content": message}).encode()
        req = urllib.request.Request(
            DISCORD_WEBHOOK_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "DiscordBot (medallion-pipeline, 1.0)",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                print(f"Discord response: {resp.status} for alarm: {alarm_name}")
        except urllib.error.HTTPError as e:
            print(f"Discord HTTP error: {e.code} {e.reason} - {e.read().decode()}")
            raise

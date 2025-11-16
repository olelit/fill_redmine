import asyncio

import aiohttp
import requests
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

REDMINE_URL = os.getenv("REDMINE_BASE_URL")
YOUTRACK_BASE_URL = os.getenv("YOTRACK_BASE_URL")


def get_data_from_youtrack_for_curr_month(youtrack_token: str):
    now = datetime.now()
    first_day = datetime(now.year, now.month, 1)

    if now.month == 12:
        last_day = datetime(now.year, 12, 31)
    else:
        first_day_next_month = datetime(now.year, now.month + 1, 1)
        last_day = first_day_next_month - timedelta(days=1)

    params = {
        "fields": "date,duration(minutes)",
        "start": int(first_day.timestamp() * 1000),
        "end": int(last_day.timestamp() * 1000),
        "$top": 500,
        "author": "me",
    }

    headers = {
        "Authorization": f"Bearer {youtrack_token}"
    }

    url = f"{YOUTRACK_BASE_URL}/api/workItems"
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()

    data = response.json()
    result = {}
    for item in data:
        date = datetime.fromtimestamp(item['date'] / 1000).strftime("%Y-%m-%d")

        if date not in result:
            result[date] = 0

        result[date] += item['duration']['minutes'] / 60
    return result


async def update_redmine_activity(uid: int, iid: int, comment: str, activity_id: int, api_key: str, records):
    url = f"{REDMINE_URL}/time_entries.xml"
    headers = {
        "Content-Type": "application/xml",
        "X-Redmine-API-Key": api_key
    }

    print("The following dates will be affected:")
    hour_sum = 0
    for date in records:
        hours = records[date]
        print(f"{date} - {hours}h")
        hour_sum += hours
    print(f"Comment: {comment}")
    print(f"Total hours: {hour_sum}")

    proceed = input("Do you want to continue? (y/n): ").strip().lower()
    if proceed != "y":
        print("Script execution stopped by the user.")
        return

    async with aiohttp.ClientSession() as session:
        tasks = []

        for date in records:
            tasks.append(set_time(session, url, headers, iid, uid, date, records[date], activity_id, comment))
        await asyncio.gather(*tasks)

async def set_time(session, url, headers, iid, uid, day, hours, activity_id, comments):
    body = f"""
<time_entry>
  <issue_id>{iid}</issue_id>
  <user_id>{uid}</user_id>
  <spent_on>{day.isoformat()}</spent_on>
  <hours>{hours}</hours>
  <activity_id>{activity_id}</activity_id>
  <comments>{comments}</comments>
</time_entry>
""".strip()
    async with session.post(url, headers=headers, data=body) as response:
        text = await response.text()
        if 200 <= response.status < 300:
            print(f"OK: {day}")
        else:
            print(f"ERROR: {day} {response.status} {text}")

async def main():
    i = 1
    while True:
        youtrack_token: str = os.getenv(f"YOUTRACK_ACCESS_TOKEN_{i}")
        uid = int(os.getenv(f"USER_ID_{i}"))
        comment = os.getenv(f"COMMENT_{i}")
        activity_id = int(os.getenv(f"ACTIVITY_ID_{i}"))
        api_key = os.getenv(f"REDMINE_API_KEY_{i}")
        iid = int(os.getenv(f"ISSUE_ID_{i}"))

        if youtrack_token is None:
            break

        records = get_data_from_youtrack_for_curr_month(youtrack_token)
        await update_redmine_activity(uid, iid, comment, activity_id, api_key, records)

        i += 1


if __name__ == '__main__':
    asyncio.run(main())

import sys
import asyncio
import aiohttp
import requests
from datetime import date, timedelta
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
import os

load_dotenv()
BASE_URL = os.getenv("REDMINE_BASE_URL")


async def update_redmine_activity(uid: int, iid: int, comment: str, activity_id: int, api_key: str):
    excludeEnv = os.getenv("EXCLUDE_DATES")
    exclude = set()

    if excludeEnv:
        exclude = set(excludeEnv.split(","))

    hours = 8
    base_url = BASE_URL
    url = f"{base_url}/time_entries.xml"
    headers = {
        "Content-Type": "application/xml",
        "X-Redmine-API-Key": api_key
    }

    today = date.today()
    first_day = today.replace(day=1)
    if first_day.month == 12:
        next_month = first_day.replace(year=first_day.year + 1, month=1, day=1)
    else:
        next_month = first_day.replace(month=first_day.month + 1, day=1)
    last_day = next_month - timedelta(days=1)

    spent_on_dates = get_times(base_url, headers, iid, uid)

    affected_dates = []
    current_day = first_day
    while current_day <= last_day:
        day_str = current_day.isoformat()
        if (
                current_day.weekday() < 5
                and day_str not in exclude
                and day_str not in spent_on_dates
        ):
            affected_dates.append(day_str)
        current_day += timedelta(days=1)

    print("The following dates will be affected:")
    for date_str in affected_dates:
        print(f"- {date_str}")
    print(f"Comment: {comment}")
    print(f"Total hours: {affected_dates.__len__() * hours}")

    proceed = input("Do you want to continue? (y/n): ").strip().lower()
    if proceed != "y":
        print("Script execution stopped by the user.")
        return

    async with aiohttp.ClientSession() as session:
        current_day = first_day
        tasks = []
        while current_day <= last_day:
            day_str = current_day.isoformat()
            if (
                    current_day.weekday() < 5
                    and day_str not in exclude
                    and day_str not in spent_on_dates
            ):
                tasks.append(set_time(session, url, headers, iid, uid, current_day, hours, activity_id, comment))
            current_day += timedelta(days=1)
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


def get_times(base_url, headers, iid, uid):
    params = {
        "user_id": uid,
        "issue_id": iid
    }
    url = f"{base_url}/time_entries.xml"
    response = requests.get(url, headers=headers, params=params)

    spent_on_dates = set()
    try:
        root = ET.fromstring(response.text)
        for entry in root.findall("time_entry"):
            spent_on = entry.find("spent_on")
            if spent_on is not None and spent_on.text:
                spent_on_dates.add(spent_on.text)
    except Exception as e:
        print(f"XML parse error: {e}")
    return spent_on_dates


async def main():
    i: int = 1
    while True:
        iid = os.getenv(f"ISSUE_ID_{i}")

        if iid is None:
            break

        uid = os.getenv(f"USER_ID_{i}")
        comment = os.getenv(f"COMMENT_{i}")
        activity_id = os.getenv(f"ACTIVITY_ID_{i}")
        api_key = os.getenv(f"REDMINE_API_KEY_{i}")
        i += 1
        await update_redmine_activity(uid, iid, comment, activity_id, api_key)


if __name__ == "__main__":
    asyncio.run(main())

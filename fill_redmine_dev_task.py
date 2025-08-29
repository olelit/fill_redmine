import sys
import asyncio
import aiohttp
import requests
from datetime import date, timedelta
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
import os

load_dotenv()
API_KEY = os.getenv("REDMINE_API_KEY")
BASE_URL = os.getenv("REDMINE_BASE_URL")


async def set_time(session, url, headers, iid, uid, day):
    body = f"""
<time_entry>
  <issue_id>{iid}</issue_id>
  <user_id>{uid}</user_id>
  <spent_on>{day.isoformat()}</spent_on>
  <hours>8</hours>
  <activity_id>9</activity_id>
  <comments>development</comments>
</time_entry>
""".strip()
    async with session.post(url, headers=headers, data=body) as response:
        await response.text()

def get_times(base_url, headers, iid, uid):
    params = {
        "user_id": uid,
        "issue_id": iid
    }
    url = f"{base_url}/time_entries.xml"
    response = requests.get(url, headers=headers, params=params)
    result = {
        "status_code": response.status_code,
        "text": response.text
    }

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
    if len(sys.argv) < 3:
        print("Usage: python fill_redmine_dev_task.py <iid> <uid> [exclude_dates]")
        sys.exit(1)
    iid = sys.argv[1]
    uid = sys.argv[2]
    exclude = set()
    if len(sys.argv) > 3:
        exclude = set(d.strip() for d in sys.argv[3].split(",") if d.strip())

    base_url = BASE_URL
    url = f"{base_url}/time_entries.xml"
    headers = {
        "Content-Type": "application/xml",
        "X-Redmine-API-Key": API_KEY
    }

    today = date.today()
    first_day = today.replace(day=1)
    if first_day.month == 12:
        next_month = first_day.replace(year=first_day.year + 1, month=1, day=1)
    else:
        next_month = first_day.replace(month=first_day.month + 1, day=1)
    last_day = next_month - timedelta(days=1)

    spent_on_dates = get_times(base_url, headers, iid, uid)

    tasks = []
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
                tasks.append(set_time(session, url, headers, iid, uid, current_day))
            current_day += timedelta(days=1)
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())

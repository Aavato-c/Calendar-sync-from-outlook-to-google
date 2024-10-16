#! /venv/bin/python3.12
import os
import sys
import logging
from datetime import datetime
from tkinter import NO

import requests
import dotenv

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account

from icalendar import Calendar

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s')
logger = logging.getLogger(__name__)

FILE_ROOT = os.path.dirname(os.path.abspath(__file__))

if not os.path.exists('.env') or not os.path.exists(f'{FILE_ROOT}/cr.json'):
    raise FileNotFoundError('Missing .env or cr.json file')

dotenv.load_dotenv()
ical_url = os.getenv("ICAL_URL")
calendar_id = os.getenv("CALENDAR_ID")
credentials = service_account.Credentials.from_service_account_file(f'{FILE_ROOT}/cr.json')

service = build('calendar', 'v3', credentials=credentials)


def fetch_ical_data(ical_url: str) -> Calendar:
    response = requests.get(ical_url)
    formatted_response = response.content.decode("utf-8")
    calendar = Calendar.from_ical(formatted_response)
    return calendar


def load_page_token(cal_id: str) -> str | None:
    path = f"{FILE_ROOT}/page_token{cal_id[0:5]}.txt"
    try:
        with open(path, 'r') as f:
            page_token = f.read()
    except FileNotFoundError:
        if not os.path.exists(path):
            with open(path, 'w') as f:
                f.write('')
            page_token = None

    return page_token


def delete_old_events(cal_id: str) -> None:
    old_events = []
    page_token = load_page_token(cal_id)
    try:
        response = service.events().list(calendarId=cal_id, pageToken=page_token).execute()
    except Exception as e:
        logger.error(f'Error fetching events: {e}')
        raise e

    counter = 0  # Just to prevent an infinite loop and to keep track of the pages
    max_counter = 300
    while True:
        counter += 1
        if counter > max_counter:
            logger.error('Max counter reached in delete_old_events. If you see this message, you should probably increase the max_counter value or check if there is an issue with the function.')
            break

        events = service.events().list(calendarId=cal_id, pageToken=page_token).execute()
        # Check if there are items in the events['items'] list
        if events['items']:
            logger.info(f'Page {counter} has {len(events["items"])} events')
        with open(f"/home/kake/koodi/kalenterisynk/page_token{cal_id[0:5]}.txt", 'w') as f:
            f.write(page_token)
        for event in events['items']:
            old_events.append(event)
            page_token = events.get('nextPageToken')
        if not page_token:
            break

    logger.info(f'Found {len(old_events)} events to delete')
    for old_event in old_events:
        try:
            service.events().delete(calendarId=cal_id, eventId=old_event['id']).execute()
            logger.debug(f'Deleted event: {old_event["summary"]}')
        except HttpError as e:
            logger.error(f'Error deleting event: {e}')
            continue
        
        logger.info(f'Deleted {len(old_events)} events')


def update_google_calendar(calendar_id, events):
    """
    The function updates the Google Calendar with the events from the ical file.
    You can customize the format of the event by changing the body dictionary.

    """
    service = build('calendar', 'v3', credentials=credentials)
    logger.info(f'Updating calendar with {len(events)} events')
    for event in events:
        neatly_formatted_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        start = event['DTSTART'].dt
        end = event['DTEND'].dt
        body = {
              'summary': str(event.get('SUMMARY')),
              'start': {
                'dateTime': start.strftime('%Y-%m-%dT%H:%M:%S'),
                'timeZone': start.tzinfo.zone
              },
              'end': {
                'dateTime': end.strftime('%Y-%m-%dT%H:%M:%S'),
                'timeZone': end.tzinfo.zone
              },
              'description': f"UPDATED: {neatly_formatted_time}\n\n{str(event.get('DESCRIPTION'))}",
              'location': str(event.get('LOCATION')),
        }
        try:
            service.events().insert(calendarId=calendar_id, body=body).execute()
            logger.debug(f'Added event: {event["SUMMARY"]}')
        except HttpError as e:
            print(f'Error updating event: {e}')
            raise e

    logger.info(f'Updated calendar with {len(events)} events')


def update_calendar(ical_url, calendar_id):
    try:
        logger.info(f'Fetching ical data from ical_url.')
        calendar = fetch_ical_data(ical_url)
    except Exception as e:
        logger.error(f'Error fetching ical data: {e}')
        events = calendar.walk('VEVENT')
        update_google_calendar(calendar_id, events)


if __name__ == "__main__":
    try:
        logger.info(f'Deleting old events at {datetime.now()}')
        delete_old_events(calendar_id)
        logger.info(f'Deleted old events at {datetime.now()}')
    except Exception as e:
        logger.error(f'Error deleting old events: {e}')
        sys.exit(1)
    
    try:
        logger.info(f'Updating calendar at {datetime.now()}')
        update_calendar(ical_url, calendar_id)
        logger.info(f'Updated calendar at {datetime.now()}')
    except Exception as e:
        logger.error(f'Error updating calendar: {e}')
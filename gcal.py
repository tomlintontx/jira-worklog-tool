from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import datetime
from utils import ( find_patterns, find_patterns_bool, send_confirmation_slack_message, make_tabular )
from redis_conn import r
import json
import slack

async def get_events_gcal(user_id: str, google_token_uri: str, google_client_id: str, google_client_secret: str, date_range: str, slack_token: str, auth_stuff: dict, client: slack.WebClient, channel_id: str) -> None:

    print('Getting events from Google Calendar...')

    if auth_stuff is None:
        # Send a message to the user
        client.chat_postMessage(channel=channel_id, text=f"You haven't authorized me yet. Try running `/setup`")
        return


    # Determine start and end dates based on date_range
    start_date = None
    end_date = None
    if (type(date_range) == list and date_range[0] == 'today') or (type(date_range) == str and date_range == 'today'):
        new_date_range = 'today'
        start_date = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z'
        end_date = datetime.datetime.utcnow().replace(hour=23, minute=59, second=59, microsecond=999999).isoformat() + 'Z'
    elif (type(date_range) == list and date_range[0] == 'yesterday') or (type(date_range) == str and date_range == 'yesterday'):
        new_date_range = 'yesterday'
        start_date = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z'
        end_date = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999).isoformat() + 'Z'
    elif date_range == 'next_seven_days':
        new_date_range = 'next_seven_days'
        start_date = (datetime.datetime.utcnow() + datetime.timedelta(days=0)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z'
        end_date = (datetime.datetime.utcnow() + datetime.timedelta(days=7)).replace(hour=23, minute=59, second=59, microsecond=999999).isoformat() + 'Z'
    elif date_range == 'last_seven_days':
        new_date_range = 'last_seven_days'
        start_date = (datetime.datetime.utcnow() - datetime.timedelta(days=8)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z'
        end_date = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999).isoformat() + 'Z'
    elif type(date_range) == list and date_range[0] == 'next':
        if date_range[1].isdigit():
            new_date_range = date_range[0] + " " + date_range[1]
            start_date = (datetime.datetime.utcnow() + datetime.timedelta(days=0)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z'
            end_date = (datetime.datetime.utcnow() + datetime.timedelta(days=int(date_range[1]))).replace(hour=23, minute=59, second=59, microsecond=999999).isoformat() + 'Z'
        else:
            # Send a message to the user
            client.chat_postMessage(channel=channel_id, text=f"Invalid date range. You provided {date_range[0]} {date_range[1]}")
            return
    elif type(date_range) == list and date_range[0] == 'last':
        if date_range[1].isdigit():
            new_date_range = date_range[0] + " " + date_range[1]
            start_date = (datetime.datetime.utcnow() - datetime.timedelta(days=int(date_range[1]))).replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z'
            end_date = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999).isoformat() + 'Z'
        else:
            # Send a message to the user
            client.chat_postMessage(channel=channel_id, text=f"Invalid date range. You provided {date_range[0]} {date_range[1]}")
            return
    else:
        # Send a message to the user
        client.chat_postMessage(channel=channel_id, text=f"Invalid date range. You provided {date_range}")
        return

    # save the start and end dates to redis by user_id as a hashset
    r.hset(f'user:{user_id}:dates', 'start_date', start_date)
    r.hset(f'user:{user_id}:dates', 'end_date', end_date)

    auth_stuff = json.loads(auth_stuff) # convert string to dict

    service = build('calendar', 'v3', credentials=Credentials(
        token=auth_stuff['access_token'],
        refresh_token=auth_stuff['refresh_token'],
        token_uri=google_token_uri,
        client_id=google_client_id,
        client_secret=google_client_secret,
        ))

    search_string = "FES"

    # Call the Calendar API
    print('Getting todays events...')
    events_result = service.events().list(calendarId='primary', timeMin=start_date, timeMax=end_date,
                                        singleEvents=True, q=search_string).execute()
    # get items from events_result
    events = events_result.get('items', [])

    fes_events = []

    # filter events that return true and append Jira key to event
    for event in events:
        cleaned_event = {}
        if find_patterns_bool(event['summary']):
            start_date = datetime.datetime.fromisoformat(event['start'].get('dateTime', event['start'].get('date')))
            start_str = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            duration = datetime.datetime.fromisoformat(end) - datetime.datetime.fromisoformat(start_str)
            event_id = event['id']
            cleaned_event = {
                'event_id': event_id,
                'summary': event['summary'],
                'start': datetime.datetime.strftime(start_date,'%Y-%m-%dT%H:%M:%S.%f%z'),
                'start_str': start_str, 
                'end': end,
                'duration': duration.seconds,
                'jira_key': find_patterns(event['summary'].upper())[0],
                'event_type': 'calendar',
                'user_id': user_id,
                'description': strip_description(event['description']) if 'description' in event else '',
            }
            fes_events.append(cleaned_event)
    
    store_events(fes_events)

    print(f'Found {len(fes_events)} events')

    if len(fes_events) == 0:
        # Send a message to the user
        client.chat_postMessage(channel=channel_id, text=f"You don't have any FES events for {new_date_range}. Remember to add the JIRA issue key to the event title in your calendar. (Example: `FES-123: My event title`)")
    else:
        # create a list of lists of events broken out by day
        final_events = []
        for event in fes_events:
            if not final_events:
                final_events.append([event])
            else:
                found = False
                for day in final_events:
                    if day[0]['start_str'][:10] == event['start_str'][:10]:
                        day.append(event)
                        found = True
                if not found:
                    final_events.append([event])
        
        final_events.sort(key=lambda day: day[0]['start_str'])

        event_ids = [event['event_id'] for event in fes_events]
        
        print(final_events)
        client.chat_postMessage(channel=channel_id, text=f'Here\'s what I found in your calendar:')

        for i in range(len(final_events)):
            tabular_events = make_tabular(final_events[i], client, user_id)
            message = f"```{tabular_events}```"
            # send a message to the user
            client.chat_postMessage(channel=channel_id, text=f"{final_events[i][0]['start_str'][:10]}:")
            client.chat_postMessage(channel=channel_id, text=message)

        # Send a message to the user
        client.chat_postMessage(channel=channel_id, blocks=send_confirmation_slack_message(event_ids))

def store_events(events: list) -> None:
    for event in events:
        event_id = event.get("event_id")  # Assuming each event has a unique 'id' field
        if event_id:
            hash_key = f"calEvent:{event_id}"
            for key, value in event.items():
                r.hset(hash_key, key, str(value))
        
        # store a date index as YYYYMMDD for each event by user_id
        user_id = event.get("user_id")
        if user_id:
            date = event.get("start_str")
            date_index = datetime.datetime.fromisoformat(date).strftime('%Y%m%d')
            r.zadd(f'user:{user_id}:calEvents', {event_id: date_index})

def strip_description(description: str) -> str:
    """
    Strips the description to find the text between the start marker <<< and the end marker >>>

    :param description: Description of a calendar event.
    :return: Stripped description.
    """
    if not description:
        return ""
    
    start_marker = "<<<"
    end_marker = ">>>"
    start_index = description.find(start_marker)
    end_index = description.find(end_marker)

    if start_index == -1 or end_index == -1:
        return ""
    
    return description[start_index + len(start_marker):end_index].strip()
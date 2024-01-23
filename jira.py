import requests
from requests.auth import HTTPBasicAuth
import json
import os
from dotenv import load_dotenv 
import redis_conn 
import slack
from utils import tabulate_dicts, make_date_friendly, get_user_timezone
import datetime

load_dotenv()

test_email = 'thomas.linton@sisense.com'

jira_url = os.environ.get('JIRA_BASE_URL')

headers = {
   "Accept": "application/json",
   "Content-Type": "application/json"
}


def create_worklog(issue_keys: list, slack_user_id: str, client: slack.WebClient, channel_id: str) -> None:

    auth_stuff = get_auth_from_redis(slack_user_id)

    gcal_event_ids = []

    # get calendar events from redis
    events = []
    keys = ['event_id', 'jira_key', 'summary', 'start', 'duration', 'jira_worklog_id', 'description']
    for event_id in issue_keys:
        event_data = redis_conn.r.hmget(f'calEvent:{event_id}',keys)
        structured_event_data = dict(zip(keys, event_data))
        events.append(structured_event_data)
        gcal_event_ids.append(event_id)

    print(f"worklog_id: {events[0]['jira_worklog_id']}")

    authentication = HTTPBasicAuth(auth_stuff['user_email'], auth_stuff['jira_api_token'])

    #get the min and max dates form redis
    min_date = datetime.datetime.fromisoformat(redis_conn.r.hget(f'user:{slack_user_id}:dates', 'start_date')[:-1] + '+00:00')
    max_date = datetime.datetime.fromisoformat(redis_conn.r.hget(f'user:{slack_user_id}:dates', 'end_date')[:-1] + '+00:00')


    # get list of stored events YYYMMDD between start and end from redis
    stored_events = redis_conn.r.zrangebyscore(f'user:{slack_user_id}:calEvents', min_date.strftime('%Y%m%d'), max_date.strftime('%Y%m%d'))

    # print stored events
    print(f'stored_events: {stored_events}')

    # compare stored events and gcal events to see if any are missing
    for event in stored_events:
        if event not in gcal_event_ids:
            # delete the worklog and cal event from redis
            worklog_id = redis_conn.r.hget(f'calEvent:{event}', 'jira_worklog_id')
            c = redis_conn.r.delete(f'calEvent:{event}')
            print(f'calEvent:{event} deleted: {c}')
            redis_conn.r.delete(f'worklog:{worklog_id}')
            redis_conn.r.zrem(f'user:{slack_user_id}:calEvents', event)

    # Make the request
    for event in events:
        # check to see if the issue is assigned to the user
        if not is_issue_assigned_to_user(event['jira_key'], slack_user_id):
            client.chat_postMessage(channel=channel_id, text=f":x: You are not assigned to `{event['jira_key']}`. Please assign yourself to the issue and try again or update your google calendar with the correct Jira Key.")
            continue

        if event.get('jira_worklog_id') is not None:
            update_worklog(event['jira_key'], event['jira_worklog_id'], generate_worklog_entry(event)['worklog_data'], authentication, event['event_id'], client, channel_id)
        else:
            
            # Construct the API endpoint URL for creating a worklog
            url = f'{jira_url}/rest/api/3/issue/{event["jira_key"]}/worklog'
            worklog_entry = generate_worklog_entry(event)
            response = requests.post(url, headers=headers, data=json.dumps(worklog_entry['worklog_data']), auth=authentication)

            # Check the response
            if response.status_code == 201:
                res = response.json()

                worklog_id = res['id']

                for key, val in res.items():
                    redis_conn.r.hset(f'worklog:{worklog_id}', key, json.dumps(val))
                
                #add the calendar event id to the worklog
                redis_conn.r.hset(f'worklog:{worklog_id}', 'event_id', event['event_id'])

                # Update the Calendar event with the worklog ID
                redis_conn.r.hset(f'calEvent:{event["event_id"]}', 'jira_worklog_id', int(worklog_id))

                # send a message to the user
                client.chat_postMessage(channel=channel_id, text=f":white_check_mark: Worklog created successfully for {event['jira_key']}.")

                print("Worklog created successfully.")
            else:
                #send a message to the user
                client.chat_postMessage(channel=channel_id, text=f":x: Failed to create worklog for {event['jira_key']}. \n Jira responded with: {response.text}")
                print("Failed to create worklog.")
                print("Response:", response.text)

def get_issue_worklogs(issue_key: str, auth_stuff: dict, channel_id: str, client: slack.WebClient, user_id: str) -> None:
    # Construct the API endpoint URL for creating a worklog
    url = f'{jira_url}/rest/api/3/issue/{issue_key}/worklog'

    # user email
    user_email = json.loads(auth_stuff)['user_email']

    #api token
    api_token = json.loads(auth_stuff)['jira_api_token']

    # todo: user user_email in production
    authentication = HTTPBasicAuth(user_email, api_token)

    # Make the request
    response = requests.get(url, headers=headers, auth=authentication)

    # Check the response
    if response.status_code == 200:
        res = response.json()

        if res['total'] == 0:
            print("No worklogs found.")
            client.chat_postMessage(channel=channel_id, text=f"No worklogs found for {issue_key}.")
            return ['No worklogs found.']

        worklogs = []

        # get user tz
        user_tz = get_user_timezone(user_id, client)

        for worklog in res['worklogs']:
            temp_dict = {
                'worklog_id': worklog['id'],
                'issue_key': issue_key.upper(),
                'author_display_name': worklog['author']['displayName'],
                'started': make_date_friendly(worklog['started'], user_tz),
                'time_spent': worklog['timeSpent'],
            }

            worklogs.append(temp_dict)

        print(f'Worklogs retrieved successfully. We found {len(worklogs)} worklogs.')

        primer = f"Here are the worklogs for {issue_key.upper()}:"
        content = f'```{tabulate_dicts(worklogs)}```'

        # Send a message to the user
        client.chat_postMessage(channel=channel_id, text=primer)
        client.chat_postMessage(channel=channel_id, text=content)

    else:
        res = response.json()
        # Send a message to the user
        client.chat_postMessage(channel=channel_id, text=f"Failed to retrieve worklogs for {issue_key.upper()}.\n Response from Jira: {res['errorMessages'][0]}")
        print("Response:", response.text)

def update_worklog(issue_key: str, worklog_id: str, worklog_data: dict, authentication: HTTPBasicAuth, event_id: str, client: slack.WebClient, channel_id: str) -> None:
    # Construct the API endpoint URL for creating a worklog
    url = f'{jira_url}/rest/api/3/issue/{issue_key}/worklog/{worklog_id}'

    # Make the request
    response = requests.put(url, headers=headers, data=json.dumps(worklog_data), auth=authentication)

    # Check the response
    if response.status_code == 200:
        res = response.json()

        for key, val in res.items():
            redis_conn.r.hset(f'worklog:{worklog_id}', key, json.dumps(val))

        cal_update = {
                'jira_worklog_id': worklog_id,
                'duration': res['timeSpentSeconds'],
                'start': res['started']
            }
        
        # Update the Calendar event with the worklog ID
        for key, value in cal_update.items():
            redis_conn.r.hset(f'calEvent:{event_id}', key, value)

        # send a message to the user
        client.chat_postMessage(channel=channel_id, text=f":white_check_mark: Worklog updated successfully for {issue_key}.")

        print("Worklog updated successfully.")
    else:
        #send a message to the user
        client.chat_postMessage(channel=channel_id, text=f"Failed to update worklog for {issue_key}. \n Jira responded with: {response.text}")
        print("Failed to update worklog.")
        print("Response:", response.text)

def generate_worklog_entry(event: dict) -> dict:
    worklog_data = {
        "comment": {
            "content": [
            {
                "content": [
                {
                    "text": event['description'] if len(event['description']) > 0 else event['summary'],
                    "type": "text"
                }
                ],
                "type": "paragraph"
            }
            ],
            "type": "doc",
            "version": 1
        },
        "started": event['start'],  # Replace with appropriate datetime
        "timeSpentSeconds": event['duration']  # Time spent in seconds (e.g., 3600 seconds for 1 hour)
    }

    # generate the worklog entry
    worklog_entry = {
        'issue_key': event['jira_key'],
        'worklog_data': worklog_data,
        'event_id': event['event_id'],
    }

    return worklog_entry

def delete_worklog_by_id(text: list, slack_user_id: str, client: slack.WebClient, channel_id: str, auth_stuff: dict) -> None:
    # get the worklog id
    worklog_id = text[1]
    issue_key = text[0]

    # get event id from redis worklog
    event_id = redis_conn.r.hget(f'worklog:{worklog_id}', 'event_id')

    # Construct the API endpoint URL for creating a worklog
    url = f'{jira_url}/rest/api/3/issue/{issue_key}/worklog/{worklog_id}'

    user_email = json.loads(auth_stuff)['user_email']
    api_token = json.loads(auth_stuff)['jira_api_token']

    # delete the worklog
    authentication = HTTPBasicAuth(user_email, api_token)
    
    # Make the request
    response = requests.delete(url, headers=headers, auth=authentication)

    # Check the response
    if response.status_code == 204:
        print("Worklog deleted successfully.")
        redis_conn.r.delete(f'worklog:{worklog_id}')
        redis_conn.r.hdel(f'calEvent:{event_id}', 'jira_worklog_id')

        #send a message to the user
        client.chat_postMessage(channel=channel_id, text=f"Worklog deleted successfully.")  
    else:
        # send a message to the user
        client.chat_postMessage(channel=channel_id, text=f"Failed to delete worklog.")
        print("Failed to delete worklog.")
        print("Response:", response.text)

def get_auth_from_redis(slack_user_id) -> dict:
    auth_stuff = json.loads(redis_conn.r.get(f'user:{slack_user_id}'))
    return auth_stuff

def is_issue_assigned_to_user(issue_key: str, slack_user_id: str) -> bool:
    auth_stuff = get_auth_from_redis(slack_user_id)

    # user email
    user_email = auth_stuff['user_email']

    #api token
    api_token = auth_stuff['jira_api_token']

    # only return the assignee field
    fields = 'assignee'

    # gather the issue data from jira
    url = f'{jira_url}/rest/api/3/issue/{issue_key}'
    authentication = HTTPBasicAuth(user_email, api_token)
    params = {'fields': fields}
    response = requests.get(url, headers=headers, auth=authentication, params=params)
    res = response.json()

    print(res)

    # check if the user is the assignee
    if type(res['fields']['assignee']) == dict:
        if res['fields']['assignee'].get('emailAddress', None) == user_email:
            return True
    else:
        return False

def parse_isoformat_with_timezone(dt_str):
    # Check if the timezone part needs to be adjusted
    if dt_str[-3] not in [":", "+", "-"]:
        # Insert a colon in the timezone part
        dt_str = dt_str[:-2] + ":" + dt_str[-2:]
    return datetime.datetime.fromisoformat(dt_str)

def get_jira_issues_for_user(auth_stuff: dict, client: slack.WebClient, channel_id: str) -> None:
    # Construct the API endpoint URL for creating a worklog
    url = f'{jira_url}/rest/api/3/search'

    # user email
    user_email = json.loads(auth_stuff)['user_email']

    #api token
    api_token = json.loads(auth_stuff)['jira_api_token']

    jql = f'assignee = "{user_email}" AND project = FES AND status in ("In Progress", "On Hold")'

    authentication = HTTPBasicAuth(user_email, api_token)

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    params = {
        'jql': jql,
        'fields': 'summary, key'
    }

    # Make the request
    response = requests.get(url, headers=headers, params=params, auth=authentication)

    # Check the response

    if response.status_code == 200:
        res = response.json()

        if res['total'] == 0:
            print("No issues found.")
            client.chat_postMessage(channel=channel_id, text=f"No issues found for {user_email}.")
            return ['No issues found.']

        issues = []

        for issue in res['issues']:
            temp_dict = {
                'issue_key': issue['key'],
                'summary': issue['fields']['summary'],
            }

            issues.append(temp_dict)

        print(f'Issues retrieved successfully. We found {len(issues)} issues.')

        primer = f"Here are the issues for {user_email}:"
        content = f'```{tabulate_dicts(issues)}```'

        # Send a message to the user
        client.chat_postMessage(channel=channel_id, text=primer)
        client.chat_postMessage(channel=channel_id, text=content)
import re
from tabulate import tabulate
import datetime
import slack
import requests
import pytz
from dateutil import parser
import os
from dotenv import load_dotenv
import textwrap

load_dotenv()

def find_pattern(text: str) -> str:
    # This regex pattern looks for sequences of uppercase letters followed by a hyphen and then one or more digits
    pattern = r'[A-Z]+-\d+'
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match:
        return match.group()
    else:
        return "No match found"
    
# return multiple matches
def find_patterns(text: str) -> list:
    pattern = r'[A-Z]+-\d+'
    return re.findall(pattern, text, flags=re.IGNORECASE)

# return true if match found
def find_patterns_bool(text: str) -> bool:
    pattern = r'[A-Z]+-\d+'
    return bool(re.search(pattern, text, flags=re.IGNORECASE))

# make mono-spaced table for slack
def make_tabular(events: list, client: slack.WebClient, user_id: str, table_format='simple_grid') -> str:
    table = []
    for event in events:
        #convert start and end to local time
        tz = get_user_timezone(user_id, client)
        start = make_date_friendly(event['start_str'], tz)
        end = make_date_friendly(event['end'], tz)
        table.append([
            textwrap.fill(event['summary'], 15), 
            textwrap.fill(event['description'].replace('\n', ' '), 25), 
            event['jira_key'], 
            start, 
            end, 
            f"{event['duration'] // 3600}:{(event['duration'] % 3600) // 60}"
        ])
    return tabulate(table, headers=['Summary', 'Description', 'Jira Key', 'Start', 'End', 'Duration'], tablefmt=table_format)

def tabulate_dicts(array_of_dicts: list[dict], table_format='github') -> str:
    """
    Generates a tabulated table from an array of dictionaries.

    :param array_of_dicts: List of dictionaries where each dictionary represents a row.
    :param table_format: Format of the table. Default is 'grid'.
    :return: String representation of the tabulated table.
    """
    if not array_of_dicts:
        return "No data provided."


    headers = array_of_dicts[0].keys()
    rows = [list(row.values()) for row in array_of_dicts]

    return tabulate(rows, headers=headers, tablefmt=table_format)

def setup_simple_text_slack_message(message: str) -> list:
    message_payload = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": message
            }
        }
    ]

    return message_payload

def send_slack_message(message: list, channel_id: str, slack_token: str) -> None:
    client = slack.WebClient(token=slack_token)
    client.chat_postMessage(channel=channel_id, blocks=message)

def send_confirmation_slack_message(event_ids: list) -> list:

    event_ids_str = "|".join(event_ids)

    print(f'event_ids_str: {event_ids_str}')

    message_payload = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Do you want to update JIRA worklogs with these entries?"
            }
        },
        {
            "type": "actions",
            "elements": [            
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Yes"
                    },
                    "value": f'{event_ids_str}',
                    "action_id": "update_jira_yes"
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "No"
                    },
                    "value": "no",
                    "action_id": "update_jira_no"
                }
            ]
        }
    ]


    return message_payload

def open_dm_channel(user_id: str, slack_token: str) -> str:
    client = slack.WebClient(token=slack_token)
    response = client.conversations_open(users=user_id)
    channel_id = response['channel']['id']

    return channel_id

def get_google_user_email(access_token: str) -> str:
    # Use the access token to fetch the user's email
    headers = {'Authorization': f'Bearer {access_token}'}
    user_info_response = requests.get('https://www.googleapis.com/oauth2/v1/userinfo', headers=headers)
    user_email = user_info_response.json().get('email')
    return user_email

def make_date_friendly(date: str, tz: pytz.timezone) -> str:
    
    parsed_date = parser.parse(date)

    # Convert the date to the user's timezone
    parsed_date = parsed_date.astimezone(tz)

    # Format the date-time in the desired friendly format
    friendly_format = parsed_date.strftime("%b %d %Y %I:%M %p %Z")

    return friendly_format

def convert_to_utc_seconds(date: str) -> int:
    # Convert the date to UTC seconds
    date_obj = datetime.datetime.strptime(date, '%Y-%m-%dT%H:%M:%S.%f%z')
    utc_seconds = int(date_obj.timestamp())
    return utc_seconds

def get_user_timezone(user_id: str, client: slack.WebClient) -> str:

    res = client.users_info(user=user_id)
    
    tz_obj = pytz.timezone(res.data['user']['tz'])

    return tz_obj

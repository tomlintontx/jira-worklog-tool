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
    """
    Finds the first occurrence of a pattern in the given text.

    Args:
        text (str): The text to search for the pattern.

    Returns:
        str: The first occurrence of the pattern found in the text, or "No match found" if no match is found.
    """
    pattern = r'[A-Z]+-\d+'
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match:
        return match.group()
    else:
        return "No match found"
    
def find_patterns(text: str) -> list:
    """
    Finds patterns matching the format of JIRA issue keys in the given text.

    Args:
        text (str): The text to search for JIRA issue keys.

    Returns:
        list: A list of JIRA issue keys found in the text.
    """
    pattern = r'[A-Z]+-\d+'
    return re.findall(pattern, text, flags=re.IGNORECASE)

def find_patterns_bool(text: str) -> bool:
    """
    Check if the given text contains a pattern in the format of 'ABC-123',
    where 'ABC' represents uppercase letters and '123' represents digits.

    Args:
        text (str): The text to search for the pattern.

    Returns:
        bool: True if the pattern is found, False otherwise.
    """
    pattern = r'[A-Z]+-\d+'
    return bool(re.search(pattern, text, flags=re.IGNORECASE))

def make_tabular(events: list, client: slack.WebClient, user_id: str, table_format='simple_grid') -> str:
    """
    Converts a list of events into a tabular format.

    Args:
        events (list): A list of events.
        client (slack.WebClient): The Slack WebClient object.
        user_id (str): The user ID.
        table_format (str, optional): The format of the table. Defaults to 'simple_grid'.

    Returns:
        str: The tabular representation of the events.
    """
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
    """
    Sets up a simple text Slack message payload.

    Args:
        message (str): The text message to be included in the payload.

    Returns:
        list: The Slack message payload in the required format.
    """
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
    """
    Sends a confirmation Slack message with buttons to update JIRA worklogs.

    Args:
        event_ids (list): A list of event IDs.

    Returns:
        list: A list representing the message payload for the Slack message.
    """

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
    """
    Opens a direct message channel with a user on Slack.

    Args:
        user_id (str): The ID of the user to open the channel with.
        slack_token (str): The Slack API token.

    Returns:
        str: The ID of the opened channel.
    """
    client = slack.WebClient(token=slack_token)
    response = client.conversations_open(users=user_id)
    channel_id = response['channel']['id']

    return channel_id

def get_google_user_email(access_token: str) -> str:
    """
    Fetches the user's email using the provided access token.

    Parameters:
    access_token (str): The access token for authentication.

    Returns:
    str: The user's email.
    """
    # Use the access token to fetch the user's email
    headers = {'Authorization': f'Bearer {access_token}'}
    user_info_response = requests.get('https://www.googleapis.com/oauth2/v1/userinfo', headers=headers)
    user_email = user_info_response.json().get('email')
    return user_email

def make_date_friendly(date: str, tz: pytz.timezone) -> str:
    """
    Converts a given date string to a friendly format based on the user's timezone.

    Args:
        date (str): The date string to be converted.
        tz (pytz.timezone): The user's timezone.

    Returns:
        str: The date in the desired friendly format.
    """
    parsed_date = parser.parse(date)

    # Convert the date to the user's timezone
    parsed_date = parsed_date.astimezone(tz)

    # Format the date-time in the desired friendly format
    friendly_format = parsed_date.strftime("%b %d %Y %I:%M %p %Z")

    return friendly_format

def convert_to_utc_seconds(date: str) -> int:
    """
    Converts a date string to UTC seconds.

    Args:
        date (str): The date string in the format '%Y-%m-%dT%H:%M:%S.%f%z'.

    Returns:
        int: The UTC seconds corresponding to the given date.

    """
    # Convert the date to UTC seconds
    date_obj = datetime.datetime.strptime(date, '%Y-%m-%dT%H:%M:%S.%f%z')
    utc_seconds = int(date_obj.timestamp())
    return utc_seconds

def get_user_timezone(user_id: str, client: slack.WebClient) -> str:
    """
    Retrieves the timezone of a user based on their user ID.

    Args:
        user_id (str): The ID of the user.
        client (slack.WebClient): The Slack WebClient instance.

    Returns:
        str: The timezone of the user.

    """
    res = client.users_info(user=user_id)
    
    tz_obj = pytz.timezone(res.data['user']['tz'])

    return tz_obj

def convert_timezone(date: datetime, tz: pytz.timezone) -> datetime:
    """
    Converts a given date to the specified timezone.

    Args:
        date (datetime): The date to be converted.
        tz (pytz.timezone): The timezone to convert the date to.

    Returns:
        datetime: The converted date in the specified timezone.
    """
    parsed_date = parser.parse(date)
    tz_obj = pytz.timezone(tz)
    parsed_date = parsed_date.astimezone(tz_obj)

    return parsed_date

def create_authorize_me_button(auth_url) -> list:
    """
    Creates a button that redirects the user to the authorization page.

    Args:
        auth_url (str): The authorization URL.

    Returns:
        list: The Slack message payload in the required format.
    """
    message_payload = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Please authorize me to access your Google Calendar."
            }
        },
        {
            "type": "actions",
            "elements": [            
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Authorize Me"
                    },
                    "url": auth_url,
                    "action_id": "authorize_me",
                    "style": "primary"
                }
            ]
        }
    ]

    return message_payload
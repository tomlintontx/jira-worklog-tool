from fastapi import FastAPI, Request, Form, BackgroundTasks, Response, responses
from gcal import get_events_gcal
import slack
from utils import get_google_user_email, open_dm_channel
import json
import requests
import urllib.parse
import secrets
import redis_conn
import os
from dotenv import load_dotenv
from jira import create_worklog, get_issue_worklogs, delete_worklog_by_id, get_jira_issues_for_user
import threading
from redis_conn import r
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',filename='slackbot.log')

load_dotenv()   

fastapi_key = os.environ.get('FASTAPI_SECRET_KEY')
google_client_id = os.environ.get('GOOGLE_CLIENT_ID')
google_client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
google_token_url = os.environ.get('GOOGLE_TOKEN_URI')
google_redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI')
google_auth_base_url = os.environ.get('GOOGLE_AUTH_BASE_URL')
slack_auth_base_url = os.environ.get('SLACK_AUTH_BASE_URL')
slack_client_id = os.environ.get('SLACK_CLIENT_ID')
slack_scopes = os.environ.get('SLACK_SCOPES')
slack_client_secret = os.environ.get('SLACK_CLIENT_SECRET')
user_scope = os.environ.get('SLACK_USER_SCOPES')

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=fastapi_key)

@app.get('/slack-authorize')
async def slack_authorize(request: Request):
    # redirect the user to the Slack authorization page with the client ID and scopes

    # create a state value to prevent CSRF attacks
    state = secrets.token_urlsafe()

    # save the state value in the user's session
    request.session['state'] = state

    params = {
        'client_id': slack_client_id,
        'scope': slack_scopes,
        'user_scope': user_scope,
        'state': state,
        'redirect_uri': 'https://fes-slackbot.sisensepoc.com/slack-oauth'
    }

    # Construct the full URL
    auth_url = slack_auth_base_url + '?' + urllib.parse.urlencode(params)

    # Redirect the user to the OAuth URL
    return responses.RedirectResponse(auth_url)

@app.get('/slack-oauth')
async def slack_oauth(request: Request):
    # Get the authorization code from the URL
    code = request.query_params['code']

    # get and parse the state
    state = request.query_params['state']

    # Get the state value from the user's session
    saved_state = request.session['state']

    # Check if the state returned by Slack matches the user's saved state
    if saved_state != state:
        return responses.RedirectResponse(url='/slack-authorize')

    # Exchange the authorization code for an access token
    response = requests.post('https://slack.com/api/oauth.v2.access',data={
        'code': code,
        'client_id': slack_client_id,
        'client_secret': slack_client_secret
    })

    print(response.json())

    # Process response
    slack_access_token = response.json().get('access_token')
    user_id = response.json().get('authed_user').get('id')
    team_id = response.json().get('team').get('id')

    # Save the access token in the database
    redis_conn.r.set(f'team:{team_id}:slack_access_token', slack_access_token)

    html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Successful</title>
        </head>
        <body>
            <p>Authentication successful. You can close this window.</p>
        </body>
        </html>
        """

    return responses.HTMLResponse(content=html_content, status_code=200)

@app.get('/')
async def index():
    return Response(status_code=200)

@app.post('/list-events')
async def list_events(background_tasks: BackgroundTasks, user_id: str = Form(...), team_id: str = Form(...), text: str = Form(default='')):
    """
    Endpoint for listing events based on the provided date range or time period.

    Args:
        background_tasks (BackgroundTasks): Background tasks to be executed.
        user_id (str): User ID.
        team_id (str): Team ID.
        text (str, optional): Text input for specifying the date range or time period. Defaults to ''.

    Returns:
        Response: HTTP response indicating the success of the request.
    """
    auth_stuff = r.get(f'user:{user_id}')
    slack_token = r.get(f'team:{team_id}:slack_access_token')
    channel_id = open_dm_channel(user_id, slack_token)
    client = slack.WebClient(token=slack_token)

    text = text.split()

    if len(text) == 0:
        # Send a message to the user
        client.chat_postMessage(channel=channel_id, text=f"Please provide a date range. Valid options are: `today`, `yesterday`, `next_seven_days`, `last_seven_days`")
        return Response(status_code=200)

    if len(text) == 1 and text[0] not in ['today', 'yesterday', 'next_seven_days', 'last_seven_days']:
        # Send a message to the user
        client.chat_postMessage(channel=channel_id, text=f"Please provide a time period. Valid options are: `today`, `yesterday`, `next_seven_days`, `last_seven_days`")
        return Response(status_code=200)
    elif len(text) == 2 and text[0] not in ['next', 'last']:
        # Send a message to the user
        client.chat_postMessage(channel=channel_id, text=f"Please provide a time period. Valid options are: `next <number of days>`, `last <number of days>`")
        return Response(status_code=200)
    elif len(text) == 1 and text[0] in ['today', 'yesterday', 'next_seven_days', 'last_seven_days']:
        # send user a message
        client.chat_postMessage(channel=channel_id, text=f"Getting events for { text[0] }...")
    elif len(text) == 2 and text[0] in ['next', 'last']:
        # send user a message
        client.chat_postMessage(channel=channel_id, text=f"Getting events for { text[0] } { text[1] }...")

    if auth_stuff is None:
        # Send a message to the user
        client.chat_postMessage(channel=channel_id, text=f"You haven't authorized me yet. Try running `/setup`")
        return Response(status_code=200)
    else:
        background_tasks.add_task(get_events_gcal, user_id, google_token_url, google_client_id, google_client_secret, text, auth_stuff, client, channel_id)

    return Response(status_code=200)

@app.post('/log-jira-worklog')
async def log_time_in_jira(background_tasks: BackgroundTasks, request: Request):
    """
    Logs time in JIRA based on the user's action in Slack.

    Args:
        background_tasks (BackgroundTasks): Background tasks to be executed.
        request (Request): The incoming request object.

    Returns:
        Response: The response object indicating the status of the request.
    """
    form_data = await request.form()
    payload = json.loads(form_data.get("payload"))
    response_url = payload['response_url']
    action_id = payload['actions'][0]['action_id'].split('|')[0]
    slack_token = r.get(f'team:{payload["team"]["id"]}:slack_access_token')
    client = slack.WebClient(token=slack_token)
    slack_user_id = payload['user']['id']
    channel_id = open_dm_channel(slack_user_id, slack_token)
    
    if action_id == 'update_jira_yes':
        # FES ticket keys
        values = payload['actions'][0]['value'].split('|')

        background_tasks.add_task(create_worklog,values, slack_user_id, client, channel_id)
        

        response_text = "Working on it..."
    elif action_id == 'update_jira_no':
        # Handle 'No' action
        response_text = ":x: JIRA worklogs will not be updated."
    else:
        response_text = "Unknown action."

    # Prepare the message update payload
    updated_message = {
        "replace_original": "true",
        "text": response_text
    }
    
    # POST request to update the original message
    response = requests.post(response_url, json=updated_message)

    if response.status_code != 200:
        print("Error updating message:", response.text)


    # Sending a simple text response back to Slack
    return Response(status_code=200)

@app.post('/testes')
async def testes(request: Request):
    request_data = await request.json()
    challenge = request_data.get('challenge', '')
    return JSONResponse(content={"challenge": challenge})

@app.post('/setup')
async def setup(user_id: str = Form(...), text: str = Form(default=''), team_id: str = Form(...)):
    """
    Endpoint for setting up the JIRA integration.

    Args:
        user_id (str): The ID of the user.
        text (str): The JIRA API token provided by the user. Defaults to an empty string.
        team_id (str): The ID of the team.

    Returns:
        Response: The response object indicating the success of the setup process.
    """
    slack_token = r.get(f'team:{team_id}:slack_access_token')
    channel_id = open_dm_channel(user_id, slack_token)

    if len(text) == 0:
        # Send a message to the user
        client = slack.WebClient(token=slack_token)
        client.chat_postMessage(channel=channel_id, text=f"Please provide your JIRA API token. You can find it here: https://id.atlassian.com/manage-profile/security/api-tokens")
        return Response(status_code=200)

    # Generate a secure, random state value
    random_state = secrets.token_urlsafe()
    state = {"state":random_state,"channel":channel_id,"user":user_id, "jira_api_token": text, "slack_token": slack_token}
    encoded_state = urllib.parse.quote(json.dumps(state))

    # Set scopes to include in the authorization request
    scopes = ['https://www.googleapis.com/auth/calendar.readonly', 'https://www.googleapis.com/auth/userinfo.email']

    # Make a list of scopes into a string
    scopes_string = ' '.join(scopes)

    # Construct the full URL
    params = {
        'client_id': google_client_id,
        'redirect_uri': google_redirect_uri,
        'response_type': 'code',
        'scope': scopes_string,
        'state': encoded_state,
        'access_type': 'offline', # If you need a refresh token
        'include_granted_scopes': 'true', # To request incremental authorization
        'prompt': 'consent' # To always prompt the user for authorization
    }

    auth_url = google_auth_base_url + '?' + urllib.parse.urlencode(params)

    # Send the user a link to the Google Auth page
    client = slack.WebClient(token=slack_token)
    client.chat_postMessage(channel=channel_id, text=f"Click here to authorize: {auth_url}")

    return Response(status_code=200)

@app.get('/oauth2callback')
async def oauth2callback(request: Request):
    """
    Callback function for OAuth2 authentication.

    Args:
        request (Request): The incoming request object.

    Returns:
        HTMLResponse: The response containing the authentication success message.
    """

    # Get the authorization code from the URL
    code = request.query_params['code']

    # get and parse the state
    state = urllib.parse.unquote(request.query_params['state'])

    state_data = json.loads(state)

    # Get the channel ID from the session
    channel_id =  state_data.get('channel', None)

    # get the user ID from from state
    user_id = state_data.get('user', None)

    # get slack token
    slack_token = state_data.get('slack_token', None)

    # Exchange the authorization code for an access token
    response = requests.post(google_token_url, json={
        'code': code,
        'client_id': google_client_id,
        'client_secret': google_client_secret,
        'redirect_uri': google_redirect_uri,
        'grant_type': 'authorization_code'
    })

    # get user email
    user_email = get_google_user_email(response.json().get('access_token'))

    # get user timezone from slack
    client = slack.WebClient(token=slack_token)
    slack_res = client.users_info(user=user_id)
    user_timezone = slack_res['user']['tz']

    # Process response
    access_token = {
        'access_token': response.json().get('access_token'),
        'refresh_token': response.json().get('refresh_token'),
        'token_uri': google_token_url,
        'user_email': user_email,
        'jira_api_token': state_data.get('jira_api_token'),
        'user_timezone': user_timezone,
    }

    # Save the access token and email in the database
    redis_conn.r.set(f'user:{user_id}', json.dumps(access_token))

    # open channel
    channel_id = open_dm_channel(user_id, slack_token)

    html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Successful</title>
        </head>
        <body>
            <p>Authentication successful. You can close this window.</p>
        </body>
        </html>
        """

    # Send a message to the user
    client = slack.WebClient(token=slack_token)
    client.chat_postMessage(channel=channel_id, text=f"You have been authorized! Try running `/list-events today` or `/list-events yesterday` to get your Google Calendar events. You can also try `/list-events next 3` or `/list-events last 7`")

    return responses.HTMLResponse(content=html_content, status_code=200)

@app.post('/get-worklogs')
async def get_worklogs(user_id: str = Form(...), team_id: str = Form(...),text: str = Form(default='') ):
    """
    Retrieves worklogs for a JIRA issue and sends them to the user on Slack.

    Parameters:
    - user_id (str): The ID of the user making the request.
    - team_id (str): The ID of the team associated with the user.
    - text (str): The JIRA issue key.

    Returns:
    - Response: A response object indicating the status of the request.
    """
    slack_token = r.get(f'team:{team_id}:slack_access_token')
    auth_stuff = r.get(f'user:{user_id}')
    channel_id = open_dm_channel(user_id, slack_token)
    client = slack.WebClient(token=slack_token)

    if len(text) == 0:
        # Send a message to the user
        client.chat_postMessage(channel=channel_id, text=f"Please provide a JIRA issue key.")
        return Response(status_code=200)

    # send user a message
    client.chat_postMessage(channel=channel_id, text=f"Getting worklogs for { text.upper() }...")

    if auth_stuff is None:
        # Send a message to the user
        client.chat_postMessage(channel=channel_id, text=f"You haven't authorized me yet. Try running `/setup`")
        return '', 200
    else:
        get_issue_worklogs(text, auth_stuff, channel_id, client, user_id)

    return Response(status_code=200)

@app.post('/delete-worklog')
async def delete_worklog(user_id: str = Form(...), team_id: str = Form(...), text: str = Form(default='')):
    """
    Deletes a worklog entry.

    Parameters:
    - user_id (str): The ID of the user making the request.
    - team_id (str): The ID of the team associated with the user.
    - text (str): The text payload containing the FES ticket number and worklog ID.

    Returns:
    - Response: The HTTP response indicating the status of the request.
    """
    slack_token = r.get(f'team:{team_id}:slack_access_token')
    auth_stuff = r.get(f'user:{user_id}')
    channel_id = open_dm_channel(user_id, slack_token)
    client = slack.WebClient(token=slack_token)

    if len(text) < 2:
        # Send a message to the user
        client.chat_postMessage(channel=channel_id, text=f"Please provide an FES ticket number and a worklog ID.")
        return Response(status_code=200)

    if auth_stuff is None:
        # Send a message to the user
        client.chat_postMessage(channel=channel_id, text=f"You haven't authorized me yet. Try running `/setup`")
        return Response(status_code=200)
    else:
        # get text payload
        text =text.split(' ')
        wls = threading.Thread(target=delete_worklog_by_id, args=(text, user_id, client, channel_id, auth_stuff))
        wls.start()

    return Response(status_code=200)

@app.post('/get-my-open-issues')
async def get_jira_issues_by_user(background_tasks: BackgroundTasks, user_id: str = Form(...), team_id: str = Form(...)):
    """
    Retrieves Jira issues for a specific user and sends them to the user's Slack channel.

    Parameters:
    - background_tasks (BackgroundTasks): Background tasks to be executed asynchronously.
    - user_id (str): The ID of the user.
    - team_id (str): The ID of the team.

    Returns:
    - Response: HTTP response indicating the status of the request.
    """
    slack_token = r.get(f'team:{team_id}:slack_access_token')
    auth_stuff = r.get(f'user:{user_id}')
    channel_id = open_dm_channel(user_id, slack_token)
    client = slack.WebClient(token=slack_token)

    if auth_stuff is None:
        # Send a message to the user
        client.chat_postMessage(channel=channel_id, text=f"You haven't authorized me yet. Try running `/setup`")
        return Response(status_code=200)
    else:
        # get text payload
        background_tasks.add_task(get_jira_issues_for_user, auth_stuff, client, channel_id)
        # send message to user
        client.chat_postMessage(channel=channel_id, text=f"Getting your open issues...")

    return Response(status_code=200)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000, log_level="info")

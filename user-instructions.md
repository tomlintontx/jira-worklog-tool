# Jira Worklogs Tool for Slack

## Introduction
The Jira Worklogs Tool is an intuitive Slackbot designed to integrate your Slack workspace with Jira and Google Calendar. It simplifies time tracking by allowing you to create, update, and manage Jira worklogs directly from Slack, using calendar events as a reference.

## Setup
Before using the Jira Worklogs Tool, you need to authenticate it with your Google Calendar and Jira account. This is a one-time setup process.

### `/setup [jira_api_token]`
- **Purpose**: Authenticate the app with Google Calendar and Jira.
- **Usage**: Run this command only once when you first start using the tool.

## Commands

### 1. `/list-events [next/last/today/yesterday] [number of days]`
- **Description**: Fetch calendar events with a Jira issue key in the title and prompt to log time in Jira.
- **Details**:
  - Lists events by day.
  - Jira issue keys format: `fes-` followed by 1 to 6 numbers.
  - Option to update Jira worklogs with these events.
  - **Warning**: Avoid double entry of time if you manually enter time in Jira.
  - **Info**: 
    - Only allows logging time against issues you are assigned to.
    - Can rectify deleted calendar events.
    - Uses meeting title or description marked by `<<< >>>` as the Jira worklog comment.
    - `next` is inclusive of the current date
    - `last` is exlusive of the current date

### 2. `/get-worklogs [jira issue key]`
- **Description**: Lists the worklogs for a specified Jira issue.

### 3. `/delete-worklog [jira issue key] [jira worklog id]`
- **Description**: Deletes a specified worklog entry from a Jira issue.

### 4. `/get-my-open-issues`
- **Description**: Returns a list of Jira issues assigned to you that are in an open or on-hold status.

## Handling Specific Scenarios

### What happens if you are added to a calendar invite that you are not the owner of?
- **Action**: Edit the calendar invite and add the relevant FES number in the title. This will update only your calendar and allow you to log your time.

### What happens if there are multiple FES resources on one calendar invite?
- **Example Scenario**: A TAM adds a solution consultant to a meeting and includes their own FES number in the title.
- **Solution**: The solution consultant should edit the calendar invite and add their FES number to the title, then save the invite. This updates only the solution consultant's calendar, allowing them to log time against their issue. If an attempt is made to log time against the wrong issue, the tool will prevent it and notify the user to either become the issue owner or change the issue number.

## Additional Information
- This tool is designed to optimize your workflow and ensure accurate time tracking.
- Regular updates and maintenance will be conducted to enhance its functionality.

## Expectations of the FES Team Member
- Please ensure to always forward log the next 7 days
- At the end of each day, you can run `/list-events today` to update what actually happened that day.

## Support
For any issues or suggestions, please contact David Hogeg.

---

Thank you for using Jira Worklogs Tool!

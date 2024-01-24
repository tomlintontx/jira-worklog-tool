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

### 2. `/get-worklogs [jira issue key]`
- **Description**: Lists the worklogs for a specified Jira issue.

### 3. `/delete-worklog [jira issue key] [jira worklog id]`
- **Description**: Deletes a specified worklog entry from a Jira issue.

### 4. `/get-my-open-issues`
- **Description**: Returns a list of Jira issues assigned to you that are in an open or on-hold status.

## Additional Information
- This tool is designed to optimize your workflow and ensure accurate time tracking.
- Regular updates and maintenance will be conducted to enhance its functionality.

## Support
For any issues or suggestions, please contact [Support Contact Information].

---

Thank you for using Jira Worklogs Tool!


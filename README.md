# AWS Reserved Capacity & Savings Plan Notifier

This [Apify Actor](https://apify.com/actors) retrieves AWS DynamoDB reserved capacities and Compute Savings Plans using the AWS SDK, then posts a summary message to a Slack channel via a bot.

## Features
- Fetches:
    - DynamoDB Reserved Capacity details
    - Compute Savings Plans (with expiration and commitment details)
- Detects and highlights upcoming expirations
- Calculates remaining days
- Sends a formatted notification to a Slack channel using a bot
- Fully configurable via Actor input

## Input Configuration

The Actor expects the following JSON input:

```json
{
    "days_urgent": 3,
    "days_reminder_short": 14,
    "days_reminder_long": 30,
    "ignored_uuids": ["5002de99-8a0f-45bf-8e1a-4c6b58cb26e4"],
    "aws_access_key_id": "ASDIOUHB53OJLK",
    "aws_secret_access_key": "********************************",
    "slack_bot_token": "********************************",
    "slack_channel_id": "ASDKJGKJ24123UZH"
}
```

| Field | Type | Required | Description |
|--------|------|-----------|-------------|
| `aws_access_key_id` | string | yes | AWS Access Key ID with permissions to query Savings Plans and DynamoDB Reserved Capacity. |
| `aws_secret_access_key` | string | yes | AWS Secret Access Key. |
| `slack_bot_token` | string | yes | Slack Bot OAuth token (used to send messages via the Slack API). |
| `slack_channel_id` | string | yes | ID of the Slack channel where notifications should be posted. |
| `days_reminder_long` | number | yes | How many days before the resource expiration to send the FIRST notification notifications. |
| `days_reminder_short` | number | yes | How many days before the resource expiration to send the SECOND notification notifications. |
| `days_urgent` | number | yes | Number of days before expiration to mark an item as urgent and spam notifications every day (default: `3`). |
| `ignored_uuids` | string[] | no | UUIDs of resources to ignore (not to send notificatons about) |



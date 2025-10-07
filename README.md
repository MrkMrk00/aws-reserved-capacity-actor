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
    "days_notify": 14,
    "aws_access_key_id": "ASDIOUHB53OJLK",
    "aws_secret_access_key": "********************************",
    "slack_bot_key": "********************************",
    "slack_channel_id": "ASDKJGKJ24123UZH"
}
```

| Field | Type | Required | Description |
|--------|------|-----------|-------------|
| `aws_access_key_id` | string | yes | AWS Access Key ID with permissions to query Savings Plans and DynamoDB Reserved Capacity. |
| `aws_secret_access_key` | string | yes | AWS Secret Access Key. |
| `slack_bot_key` | string | yes | Slack Bot OAuth token (used to send messages via the Slack API). |
| `slack_channel_id` | string | yes | ID of the Slack channel where notifications should be posted. |
| `days_notify` | number | yes | Number of days before expiration to send a reminder (default: `14`). |
| `days_urgent` | number | yes | Number of days before expiration to mark an item as urgent and spam notifications every day (default: `3`). |



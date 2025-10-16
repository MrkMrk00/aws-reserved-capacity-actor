# AWS Reserved Capacity & Savings Plan Notifier

This [Apify Actor](https://apify.com/actors) retrieves AWS DynamoDB reserved capacities and Compute Savings Plans using the AWS SDK, then posts a summary message to a Slack channel via a bot.

## Installation
For development a `Makefile` is provided.

```{bash}
PY_EXE=python3.13 make install
```

`make install` command with create a virtual environment `-m venv` and install development dependencies. (To install production dependencies only use `pip install -r requirements.txt`.)

You can configure the Python executable, that will be used when creating the venv with the `PY_EXE` env variable.

```{bash}
make lint
```
This will run some linting tools and return with exit code `1` when any of them fail:
- `mypy`
- `flake8`
- `isort`

To run the Actor locally first enter the `venv` with `. ./venv/bin/activate` and then use the [Apify CLI](https://docs.apify.com/cli/) and provide a valid input. (e.g. `apify run --input-file=./input.json`)

## Features
- Fetches:
    - DynamoDB Reserved Capacity details
    - Compute Savings Plans (with expiration and commitment details)
- Detects and highlights upcoming expirations
- Sends a formatted notification to a Slack channel using a bot
    - 3 rounds of notifications (dates configurable) - LONG, SHORT and URGENT
    - "urgent" notification period = notifications get sent every day before resource expiration
- Fully configurable via Actor input

## Input Configuration

! Make sure the Slack app has the following permissions:
- `chat:write`
- `users:read`
- `users:read.email`

The Actor expects the following JSON input:

```{json}
{
    "days_urgent": 3,
    "days_reminder_short": 14,
    "days_reminder_long": 30,
    "ignored_uuids": ["5002de99-8a0f-45bf-8e1a-4c6b58cb26e4"],
    "aws_access_key_id": "ASDIOUHB53OJLK",
    "aws_secret_access_key": "********************************",
    "slack_bot_token": "********************************",
    "aws_account_region": "us-east-1",
    "slack_channel_id": "ASDKJGKJ24123UZH",
    "default_owner": "someone@example.com",
    "store_name": "slack-notifications",
    "target_resource": "dynamodb_reserved_capacity"
}
```

| Field | Type | Required | Description |
|--------|------|-----------|-------------|
| `aws_access_key_id` | string | yes | AWS Access Key ID with permissions to query Savings Plans and DynamoDB Reserved Capacity. |
| `aws_secret_access_key` | string | yes | AWS Secret Access Key. |
| `aws_account_region` | string | yes | Region of the AWS account. |
| `slack_bot_token` | string | yes | Slack Bot OAuth token (used to send messages via the Slack API). |
| `slack_channel_id` | string | yes | ID of the Slack channel where notifications should be posted. |
| `days_reminder_long` | number | yes | How many days before the resource expiration to send the FIRST notification notifications. |
| `days_reminder_short` | number | yes | How many days before the resource expiration to send the SECOND notification notifications. |
| `days_urgent` | number | yes | Number of days before expiration to mark an item as urgent and spam notifications every day (default: `3`). |
| `target_resource` | string | yes | Which AWS savings resource to monitor. |
| `ignored_uuids` | string[] | no | UUIDs of resources to ignore (not to send notificatons about) |
| `default_owner` | string | no | The email address of the default owner to tag in the notification. (if not present in `tags.owner`) |
| `store_name` | string | no | Name of the key-value store in which to store the UUIDs of already notified resources. |



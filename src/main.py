import asyncio
import os

import boto3
import slack_sdk
from apify import Actor
from crawlee.storages import KeyValueStore

from .aws import Expiriable, SavingsRepository
from .notifications import (Notification, cleanup_kv_store,
                            create_notification_text, get_expiring_soon,
                            mark_resources_as_notified)

ORG_ACCOUNT_REGION = 'us-east-1'
STORE_NAME = 'slack-notifications'


def create_aws_session(actor_input: dict) -> boto3.Session:
    access_key_id = actor_input.get('aws_access_key_id',
                                    os.environ.get('AWS_ACCESS_KEY_ID'))
    secret_access_key = actor_input.get('aws_secret_access_key',
                                        os.environ.get('AWS_SECRET_ACCESS_KEY'))

    assert access_key_id is not None and secret_access_key is not None, \
        'AWS access token was not provided'

    return boto3.Session(
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name=ORG_ACCOUNT_REGION,
    )


async def handle_slack_notification(
    notification_type: Notification,
    resources: list[Expiriable],
    store: KeyValueStore,
    client: slack_sdk.WebClient,
    channel_name: str,
    default_owner: str | None,
) -> None:
    text = await create_notification_text(
        notification=notification_type,
        slack=client,
        resources=resources,
        default_owner=default_owner,
    )

    if os.environ.get('DEBUG'):
        print(f'Notification ({notification_type.value}): \n{text}')

        return

    await asyncio.to_thread(
        client.chat_postMessage,
        channel=channel_name,
        markdown_text=text,
    )
    await mark_resources_as_notified(notification_type, store, resources)


async def main() -> None:
    async with Actor:
        input = await Actor.get_input()

        default_owner = input.get('default_owner')
        slack_bot_token = input.get(
            'slack_bot_token', os.environ.get('SLACK_BOT_TOKEN'))
        assert slack_bot_token is not None, \
            'Slack bot token was not provided'

        slack_channel_id = input.get(
            'slack_channel_id', os.environ.get('SLACK_CHANNEL_ID'))
        assert slack_channel_id is not None, \
            'Slack channel id was not provided'

        session = create_aws_session(input)
        store: KeyValueStore = await Actor.open_key_value_store(name=STORE_NAME)
        slack = slack_sdk.WebClient(token=slack_bot_token)
        savings_repo = SavingsRepository(session)

        savings_repo.ignore_uuids(input.get('ignored_uuids', []))

        savings_resources: list[Expiriable] = list(await savings_repo.collect_resources())
        if len(savings_resources) <= 0:
            Actor.log.info('no notifications to be send, skipping')
            return

        notification_futures = []

        # ==================== LONG NOTIFICATION
        long_reminder_delta = Notification.REMINDER_LONG.notify_delta(input)
        long_notified_ids: set[str] = set(await store.get_value(Notification.REMINDER_LONG.store_key, []))  # noqa: E501
        to_notify_long = list(get_expiring_soon(
            savings_resources, long_reminder_delta, ignore_ids=long_notified_ids))

        if len(to_notify_long) > 0:
            notification_futures.append(handle_slack_notification(
                Notification.REMINDER_LONG,
                resources=to_notify_long,
                store=store,
                client=slack,
                channel_name=slack_channel_id,
                default_owner=default_owner,
            ))
        # ====================

        # ==================== SHORT NOTIFICATION
        short_reminder_delta = Notification.REMINDER_SHORT.notify_delta(input)
        short_notified_ids: set[str] = set(await store.get_value(Notification.REMINDER_SHORT.store_key, []))  # noqa: E501
        to_notify_short = list(get_expiring_soon(
            savings_resources, short_reminder_delta, ignore_ids=short_notified_ids))

        if len(to_notify_short) > 0:
            notification_futures.append(handle_slack_notification(
                Notification.REMINDER_SHORT,
                resources=to_notify_short,
                store=store,
                client=slack,
                channel_name=slack_channel_id,
                default_owner=default_owner,
            ))

        # ==================== URGENT NOTIFICATION
        urgent_reminder_delta = Notification.URGENT.notify_delta(input)
        to_notify_urgently = list(get_expiring_soon(
            savings_resources, urgent_reminder_delta))

        if len(to_notify_urgently) > 0:
            notification_futures.append(handle_slack_notification(
                Notification.URGENT,
                resources=to_notify_urgently,
                store=store,
                client=slack,
                channel_name=slack_channel_id,
                default_owner=default_owner,
            ))
        # ====================

        await asyncio.gather(*notification_futures)
        await cleanup_kv_store(Notification.REMINDER_LONG, store, savings_resources)
        await cleanup_kv_store(Notification.REMINDER_SHORT, store, savings_resources)

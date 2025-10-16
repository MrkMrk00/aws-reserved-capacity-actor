import asyncio
import dataclasses
import os

import boto3
import slack_sdk
from apify import Actor
from crawlee.storages import KeyValueStore

from .aws import Expiriable, SavingsRepository, SupportedResource
from .notifications import (Notification, cleanup_kv_store,
                            create_notification_text, get_expiring_soon,
                            mark_resources_as_notified)


@dataclasses.dataclass
class Input:
    days_reminder_long: int
    days_reminder_short: int
    days_urgent: int
    slack_bot_token: str
    slack_channel_id: str
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_account_region: str
    # TODO: for improvement, allow multiple resources
    target_resource: SupportedResource
    ignored_uuids: list[str] = dataclasses.field(default_factory=list)
    default_owner: str | None = None
    store_name: str = 'slack-notifications'


def create_aws_session(input: Input) -> boto3.Session:
    return boto3.Session(
        aws_access_key_id=input.aws_access_key_id,
        aws_secret_access_key=input.aws_secret_access_key,
        region_name=input.aws_account_region,
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
        input = Input(**await Actor.get_input())

        session = create_aws_session(input)
        store: KeyValueStore = await Actor.open_key_value_store(name=input.store_name)
        slack = slack_sdk.WebClient(token=input.slack_bot_token)
        savings_repo = SavingsRepository(session)

        savings_repo.ignore_uuids(input.ignored_uuids)

        savings_resources: list[Expiriable] = list(await savings_repo.collect_resources(
            (input.target_resource, ),
        ))
        if len(savings_resources) <= 0:
            Actor.log.info('no notifications to be send, skipping')
            return

        notification_futures = []

        # ==================== LONG NOTIFICATION
        long_reminder_delta = Notification.REMINDER_LONG.notify_delta(
            input.__dict__,
        )
        long_notified_ids: set[str] = set(await store.get_value(Notification.REMINDER_LONG.store_key, []))  # noqa: E501
        to_notify_long = list(get_expiring_soon(
            savings_resources, long_reminder_delta, ignore_ids=long_notified_ids))

        if len(to_notify_long) > 0:
            notification_futures.append(handle_slack_notification(
                Notification.REMINDER_LONG,
                resources=to_notify_long,
                store=store,
                client=slack,
                channel_name=input.slack_channel_id,
                default_owner=input.default_owner,
            ))
        # ====================

        # ==================== SHORT NOTIFICATION
        short_reminder_delta = Notification.REMINDER_SHORT.notify_delta(
            input.__dict__,
        )
        short_notified_ids: set[str] = set(await store.get_value(Notification.REMINDER_SHORT.store_key, []))  # noqa: E501
        to_notify_short = list(get_expiring_soon(
            savings_resources, short_reminder_delta, ignore_ids=short_notified_ids))

        if len(to_notify_short) > 0:
            notification_futures.append(handle_slack_notification(
                Notification.REMINDER_SHORT,
                resources=to_notify_short,
                store=store,
                client=slack,
                channel_name=input.slack_channel_id,
                default_owner=input.default_owner,
            ))

        # ==================== URGENT NOTIFICATION
        urgent_reminder_delta = Notification.URGENT.notify_delta(
            input.__dict__,
        )
        to_notify_urgently = list(get_expiring_soon(
            savings_resources, urgent_reminder_delta))

        if len(to_notify_urgently) > 0:
            notification_futures.append(handle_slack_notification(
                Notification.URGENT,
                resources=to_notify_urgently,
                store=store,
                client=slack,
                channel_name=input.slack_channel_id,
                default_owner=input.default_owner,
            ))
        # ====================

        await asyncio.gather(*notification_futures)
        await cleanup_kv_store(Notification.REMINDER_LONG, store, savings_resources)
        await cleanup_kv_store(Notification.REMINDER_SHORT, store, savings_resources)

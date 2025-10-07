import asyncio
import datetime
import os
from typing import Generator, Iterable

import boto3
import slack_sdk
from apify import Actor
from crawlee.storages import KeyValueStore

from .aws import (Expiriable, ReservedCapacity, SavingsPlan,
                  list_dynamodb_reserved_capacities, list_savings_plans)

ORG_ACCOUNT_REGION = 'us-east-1'
STORE_NAME = 'slack-notifications'
SENT_NOTIFICATIONS_KEY = 'notifications-sent'


def get_expiring_soon(
        capacities: Iterable[Expiriable],
        notify_period: datetime.timedelta) -> Generator[ReservedCapacity]:
    for capacity in capacities:
        now = datetime.datetime.now().astimezone()
        valid_until = capacity.valid_until()

        if not capacity.is_active() or valid_until < now:
            continue

        #                V(now+notify_period)
        # ---|--------|--|-----
        #    ^now     ^valid_until

        if valid_until <= now + notify_period:
            yield capacity


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


async def handle_notify_urgent(client: slack_sdk.WebClient,
                               channel_name: str,
                               store: KeyValueStore,
                               delta: datetime.timedelta,
                               saving_plans: list[Expiriable]):
    urgent_plans = list(get_expiring_soon(saving_plans, delta))

    if len(urgent_plans) <= 0:
        Actor.log.info('no urgent notifications to be sent')
        return

    text = """\
Hey!
These AWS savings plans will be expiring very soon! You might want to renew them.

"""
    now = datetime.datetime.now().astimezone()

    for plan in urgent_plans:
        days_remaining = (plan.valid_until() - now).days

        text += f'- {plan.describe()} (expiring in **{days_remaining}** days)\n'

    Actor.log.info(f'sending urgent notification\n{text=}')

    return await asyncio.to_thread(client.chat_postMessage,
                                   channel=channel_name,
                                   markdown_text=text.strip())


async def handle_notify_non_urgent(client: slack_sdk.WebClient,
                                   channel_name: str,
                                   store: KeyValueStore,
                                   delta: datetime.timedelta,
                                   saving_plans: list[Expiriable]):
    sent_ids = set(await store.get_value(SENT_NOTIFICATIONS_KEY, []))
    non_urgent_plans = list(get_expiring_soon(
        filter(lambda sp: sp.get_id() not in sent_ids, saving_plans),
        delta
    ))

    if len(non_urgent_plans) <= 0:
        Actor.log.info('no non_urgent notifications to be sent')
        return

    text = """\
Hi.
There seem to be some savings plans in AWS that will be expiring soon. Just letting you know ;)

"""
    for plan in non_urgent_plans:
        text += f'- {plan.describe()}\n'

    Actor.log.info(f'sending non_urgent notification\n{text=}')

    result = await asyncio.to_thread(client.chat_postMessage,
                                     channel=channel_name,
                                     markdown_text=text.strip())

    # save the new ids into sent notification
    #    -> do not send this notification multiple times
    new_ids = [*(plan.get_id() for plan in non_urgent_plans), *sent_ids]
    await store.set_value(SENT_NOTIFICATIONS_KEY, new_ids)

    return result


async def main() -> None:
    async with Actor:
        input = await Actor.get_input()

        slack_bot_token = input.get('slack_bot_token', os.environ.get('SLACK_BOT_TOKEN'))
        assert slack_bot_token is not None, \
            'Slack bot token was not provided'

        slack_channel_id = input.get('slack_channel_id', os.environ.get('SLACK_CHANNEL_ID'))
        assert slack_channel_id is not None, \
            'Slack channel id was not provided'

        session = create_aws_session(input)
        store: KeyValueStore = await Actor.open_key_value_store(name=STORE_NAME)
        slack = slack_sdk.WebClient(token=slack_bot_token)

        reserved_capacities: list[ReservedCapacity]
        savings_plans: list[SavingsPlan]

        reserved_capacities, savings_plans = await asyncio.gather(
            list_dynamodb_reserved_capacities(session, ORG_ACCOUNT_REGION),
            list_savings_plans(session, ORG_ACCOUNT_REGION),
        )

        all_savings_plans = [*reserved_capacities, *savings_plans]
        if len(all_savings_plans) <= 0:
            Actor.log.info('no notifications to be send, skipping')
            return

        non_urgent_notify_delta = datetime.timedelta(days=input.get('days_notify'))
        urgent_delta = datetime.timedelta(days=input.get('days_urgent'))

        non_urgent_future = handle_notify_non_urgent(
            client=slack,
            channel_name=slack_channel_id,
            store=store,
            delta=non_urgent_notify_delta,
            saving_plans=all_savings_plans
        )

        urgent_future = handle_notify_urgent(
            client=slack,
            channel_name=slack_channel_id,
            store=store,
            delta=urgent_delta,
            saving_plans=all_savings_plans
        )

        await asyncio.gather(non_urgent_future, urgent_future)

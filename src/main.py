import asyncio
import dataclasses
import datetime
import os
import pprint
from typing import Generator

import boto3
# import slack_sdk
from apify import Actor

from .aws import (ReservedCapacity, SavingsPlan,
                  list_dynamodb_reserved_capacities, list_savings_plans)


def get_expiring_soon(
        capacities: list[ReservedCapacity],
        notify_period: datetime.timedelta) -> Generator[ReservedCapacity]:
    for capacity in capacities:
        now = datetime.datetime.now()
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
    )


# def send_slack_notification(bot_token: str) -> None:
#     client = slack_sdk.WebClient(token=bot_token)
#
#     client.chat_postMessage(
#         channel=)


ORG_ACCOUNT_REGION = 'us-east-1'


async def main() -> None:
    async with Actor:
        input = await Actor.get_input()

        # slack_bot_token = input.get('slack_bot_token', os.environ.get('SLACK_BOT_TOKEN'))
        # assert slack_bot_token is not None, \
        #     'Slack bot token was not provided'

        session = create_aws_session(input)

        reserved_capacities: list[ReservedCapacity]
        savings_plans: list[SavingsPlan]

        reserved_capacities, savings_plans = await asyncio.gather(
            list_dynamodb_reserved_capacities(session, ORG_ACCOUNT_REGION),
            list_savings_plans(session, ORG_ACCOUNT_REGION),
        )

        pprint.pprint({
            'reserved_capacities': reserved_capacities,
            'savings_plans': savings_plans,
        })

        expiring_soon = list(get_expiring_soon(
            reserved_capacities, datetime.timedelta(days=input.get('days'))))

        Actor.log.info('%d DynamoDB reserved capacities expiring soon',
                       len(expiring_soon))

        if len(expiring_soon) == 0:
            return

        pprint.pprint(list(expiring_soon))

        await Actor.push_data(
            [dataclasses.asdict(it) for it in expiring_soon]
        )

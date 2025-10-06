import dataclasses
import datetime
import pprint
from typing import Generator

import boto3
from apify import Actor

from .aws import CustomAwsClient, ReservedCapacity


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


async def main() -> None:
    async with Actor:
        input = await Actor.get_input()

        client = CustomAwsClient(boto3.Session(), region='us-east-1')
        reserved_capacities = client.dynamodb_reserved_capacities()

        expiring_soon = get_expiring_soon(
            reserved_capacities, datetime.timedelta(days=input.get('days')))

        pprint.pprint(list(expiring_soon))

        await Actor.push_data(
            [dataclasses.asdict(it) for it in expiring_soon]
        )

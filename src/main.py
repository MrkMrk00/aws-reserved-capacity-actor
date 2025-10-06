import dataclasses

import boto3
from apify import Actor

from .aws import CustomAwsClient


async def main() -> None:
    async with Actor:
        _ = await Actor.get_input()

        client = CustomAwsClient(boto3.Session(), region='us-east-1')
        reserved_capacities = client.dynamodb_reserved_capacities()

        await Actor.push_data(
            [dataclasses.asdict(it) for it in reserved_capacities]
        )

import asyncio
import pprint

import boto3
from apify import Actor

from .aws import CustomAwsClient

ORG_REGION = 'us-east-1'


"""
    Login to AWS (secret + VPN? + ENV?)
        -> fetch reserved capacities
        -> find those that are going to expire soon
            -> if there are some, send a notification to Slack
"""


async def main() -> int:
    client = CustomAwsClient(boto3.Session(), ORG_REGION)
    async with Actor:
        pass

    # result = client.dynamodb_reserved_capacities()
    # pprint.pprint(result)

    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))

import abc
import asyncio
import dataclasses
import datetime
import http
import json
import urllib
from typing import Self, override

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


class Expiriable(abc.ABC):
    @abc.abstractmethod
    def get_id(self) -> str: ...

    @abc.abstractmethod
    def get_link(self, region: str = 'us-east-1') -> str: ...

    @abc.abstractmethod
    def is_active(self) -> bool: ...

    @abc.abstractmethod
    def start_date(self) -> datetime.datetime: ...

    @abc.abstractmethod
    def valid_until(self) -> datetime.datetime: ...

    @abc.abstractmethod
    def describe(self) -> str: ...


class FromDictMixin:
    @classmethod
    def from_dict(cls, dct: dict) -> Self:
        # unsure no extra fields in dct
        fields = {field.name for field in dataclasses.fields(cls)}
        data = {k: v for k, v in dct.items() if k in fields}

        return cls(**data)


@dataclasses.dataclass
class ReservedCapacity(FromDictMixin, Expiriable):
    DurationSeconds: int
    FixedPrice: float
    InstanceCount: int
    ReservedCapacityId: str
    ReservedCapacityState: str
    StartDate: str
    UsagePrice: float
    UsageType: str

    @override
    def get_link(self, region: str = 'us-east-1') -> str:
        return f'https://{region}.console.aws.amazon.com/dynamodbv2/home?region={region}#reserved-capacity'  # noqa: E501

    @override
    def get_id(self) -> str:
        return self.__class__.__name__ + self.ReservedCapacityId

    @override
    def is_active(self) -> bool:
        return self.ReservedCapacityState == 'active'

    @override
    def valid_until(self) -> datetime.datetime:
        valid_delta = datetime.timedelta(seconds=int(self.DurationSeconds))

        return self.start_date() + valid_delta

    @override
    def describe(self) -> str:
        return f'DynamoDB Reserved Capacity for ${self.upfront_cost():.2f}'

    @override
    def start_date(self) -> datetime.datetime:
        unix_timestamp = int(self.StartDate) / 1000

        return datetime.datetime.fromtimestamp(unix_timestamp, datetime.timezone.utc)

    def upfront_cost(self):
        return self.FixedPrice * self.InstanceCount


_RPC_RESERVED_CAPACITY = 'ReservedCapacity_20120810.DescribeReservedCapacity'


async def _make_custom_request(
        session: boto3.Session,
        region: str,
        service: str,
        rpc_target: str,
        method: str = 'POST',
        body: dict = {}) -> dict | None:
    credentials = session.get_credentials().get_frozen_credentials()

    url = f'https://{service}.{region}.amazonaws.com/'
    headers = {
        'Host': f'{service}.{region}.amazonaws.com',
        'Content-Type': 'application/x-amz-json-1.0',
        'X-Amz-Target': rpc_target,
    }
    body = json.dumps(body).encode()

    request = AWSRequest(method=method, url=url,
                         data=body, headers=headers)

    SigV4Auth(credentials, service_name=service,
              region_name=region).add_auth(request)

    prepared_headers = dict(request.headers.items())

    request = urllib.request.Request(
        method=method,
        url=url,
        data=body,
        headers=prepared_headers,
    )

    def _do_fetch(req: urllib.request.Request):
        with urllib.request.urlopen(req) as res:
            res: http.client.HTTPResponse
            assert res.status >= 200 and res.status < 300, res.read().decode()

            return json.loads(res.read().decode())

    return await asyncio.to_thread(_do_fetch, request)


async def list_dynamodb_reserved_capacities(
        session: boto3.Session,
        region: str) -> list[ReservedCapacity]:
    objects = []

    start_key = 0
    while True:
        response = await _make_custom_request(
            session,
            region,
            'dynamodb',
            _RPC_RESERVED_CAPACITY,
            body={'ExclusiveStartKey': str(start_key)},
        )

        objects.extend(ReservedCapacity.from_dict(json_capacity)
                       for json_capacity in response.get('ReservedCapacities'))

        next_pager = int(response.get('LastEvaluatedKey'))

        # no more items to fetch
        if next_pager - start_key > len(response.get('ReservedCapacities')):
            break
        else:
            start_key = next_pager

    return objects


@dataclasses.dataclass
class SavingsPlan(FromDictMixin, Expiriable):
    commitment: str
    description: str
    # start/end has format '2026-11-06T12:59:59.000Z'
    start: str
    end: str
    offeringId: str
    savingsPlanId: str
    savingsPlanType: str
    state: str

    @override
    def get_link(self, region: str = 'us-east-1') -> str:
        return f'https://{region}.console.aws.amazon.com/costmanagement/home#/savings-plans/inventory'  # noqa: E501

    @override
    def get_id(self) -> str:
        return self.__class__.__name__ + self.savingsPlanId

    @override
    def is_active(self) -> bool:
        return self.state == 'active'

    @override
    def valid_until(self) -> datetime.datetime:
        return datetime.datetime.fromisoformat(self.end)

    @override
    def describe(self) -> str:
        return f'{self.description} for ${float(self.commitment):.2f}'

    @override
    def start_date(self) -> datetime.datetime:
        return datetime.datetime.fromisoformat(self.start)


async def list_savings_plans(session: boto3.Session, region: str) -> list[SavingsPlan]:
    max_results = 1000
    objects: list[SavingsPlan] = []
    pager = None
    client = session.client('savingsplans', region_name=region)

    while True:
        params = {'maxResults': max_results}
        if pager is not None:
            params['nextToken'] = pager

        response = await asyncio.to_thread(client.describe_savings_plans, **params)

        savings_plans = response['savingsPlans']
        if len(savings_plans) == 0:
            break

        objects.extend(SavingsPlan.from_dict(sp) for sp in savings_plans)

        if len(savings_plans) >= max_results and 'nextToken' in response:
            pager = response['nextToken']
        else:
            break

    return objects

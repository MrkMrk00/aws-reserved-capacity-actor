import abc
import asyncio
import dataclasses
import datetime
import enum
import http
import itertools
import json
import urllib.request
from typing import Coroutine, Iterable, Self, cast, override

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


@dataclasses.dataclass
class Description:
    title: str
    blocks: Iterable[str] = tuple()


class Expiriable(abc.ABC):
    @abc.abstractproperty
    def id(self) -> str: ...

    @abc.abstractproperty
    def owner(self) -> str | None: ...

    @abc.abstractmethod
    def get_link(self, region: str = 'us-east-1') -> str: ...

    @abc.abstractmethod
    def is_active(self) -> bool: ...

    @abc.abstractmethod
    def start_date(self) -> datetime.datetime: ...

    @abc.abstractmethod
    def valid_until(self) -> datetime.datetime: ...

    @abc.abstractmethod
    def describe(self) -> Description: ...


class FromDictMixin:
    @classmethod
    def from_dict(cls, dct: dict) -> Self:
        if not dataclasses.is_dataclass(cls):
            raise TypeError(f'{cls.__name__} is not a dataclass')

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

    @property
    def id(self) -> str:
        return self.ReservedCapacityId

    @property
    def owner(self) -> str | None:
        return None

    @override
    def is_active(self) -> bool:
        return self.ReservedCapacityState == 'active'

    @override
    def valid_until(self) -> datetime.datetime:
        valid_delta = datetime.timedelta(seconds=int(self.DurationSeconds))

        return self.start_date() + valid_delta

    @override
    def describe(self) -> Description:
        days_remaining = (self.valid_until() - self.start_date()).days
        start_date = self.start_date().strftime('%Y-%m-%d')

        return Description(
            title=f'DynamoDB Reserved Capacity for ${self.upfront_cost():.2f}',
            blocks=(
                f'ID: `{self.id}`',
                f'Expiring in {days_remaining} days; bought: {start_date}',
            )
        )

    @override
    def start_date(self) -> datetime.datetime:
        unix_timestamp = int(self.StartDate) / 1000

        return datetime.datetime.fromtimestamp(unix_timestamp, datetime.timezone.utc)

    def upfront_cost(self):
        return self.FixedPrice * self.InstanceCount


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
    tags: dict[str, str]

    @override
    def get_link(self, region: str = 'us-east-1') -> str:
        return f'https://{region}.console.aws.amazon.com/costmanagement/home#/savings-plans/inventory'  # noqa: E501

    @property
    def id(self) -> str:
        return self.savingsPlanId

    @property
    def owner(self) -> str | None:
        return self.tags.get('owner')

    @override
    def is_active(self) -> bool:
        return self.state == 'active'

    @override
    def valid_until(self) -> datetime.datetime:
        return datetime.datetime.fromisoformat(self.end)

    @override
    def describe(self) -> Description:
        days_remaining = (self.valid_until() - self.start_date()).days
        start_date = self.start_date().strftime('%Y-%m-%d')
        tags_as_str = ', '.join(f'`{k}={v}`' for k, v in self.tags.items())

        return Description(
            title=f'{self.description} for ${float(self.commitment):.2f}',
            blocks=(
                f'ID: `{self.id}`',
                f'Expiring in {days_remaining} days; bought: {start_date}',
                f'Tags: {tags_as_str}',
            )
        )

    @override
    def start_date(self) -> datetime.datetime:
        return datetime.datetime.fromisoformat(self.start)


async def _make_custom_request(
        session: boto3.Session,
        region: str,
        service: str,
        rpc_target: str,
        method: str = 'POST',
        body: dict = {}) -> dict | None:
    credentials = session.get_credentials()
    assert credentials is not None

    frozen_credentials = credentials.get_frozen_credentials()

    url = f'https://{service}.{region}.amazonaws.com/'
    headers = {
        'Host': f'{service}.{region}.amazonaws.com',
        'Content-Type': 'application/x-amz-json-1.0',
        'X-Amz-Target': rpc_target,
    }
    body_encoded = json.dumps(body).encode()

    aws_request = AWSRequest(method=method, url=url,
                             data=body_encoded, headers=headers)

    SigV4Auth(frozen_credentials, service_name=service,
              region_name=region).add_auth(aws_request)

    prepared_headers = dict(aws_request.headers.items())

    request = urllib.request.Request(
        method=method,
        url=url,
        data=body_encoded,
        headers=prepared_headers,
    )

    def _do_fetch(req: urllib.request.Request):
        res: http.client.HTTPResponse
        with urllib.request.urlopen(req) as res:
            assert res.status >= 200 and res.status < 300, res.read().decode()

            return json.loads(res.read().decode())

    return await asyncio.to_thread(_do_fetch, request)


class SupportedResource(enum.StrEnum):
    DYNAMODB_RESERVED_CAPACITY = enum.auto()
    COMPUTE_SAVINGS_PLAN = enum.auto()

    @classmethod
    def all(cls) -> Iterable['SupportedResource']:
        return (r for r in cls)


class SavingsRepository:
    _RPC_RESERVED_CAPACITY = 'ReservedCapacity_20120810.DescribeReservedCapacity'

    def __init__(self, session: boto3.Session):
        self._session = session
        self._ignored_uuids: set[str] = set()

    async def _list_dynamodb_reserved_capacities(self) -> list[ReservedCapacity]:
        objects: list[ReservedCapacity] = []
        pager = 0

        while True:
            response = await _make_custom_request(
                self._session,
                self._session.region_name,
                'dynamodb',
                self._RPC_RESERVED_CAPACITY,
                body={'ExclusiveStartKey': str(pager)},
            )

            assert response is not None

            objects.extend(ReservedCapacity.from_dict(json_capacity)
                           for json_capacity in response.get('ReservedCapacities', []))

            next_pager = int(response.get('LastEvaluatedKey', '-1'))
            if next_pager - pager > len(response.get('ReservedCapacities', [])):
                break
            else:
                pager = next_pager

        return objects

    async def _list_savings_plans(self) -> list[SavingsPlan]:
        max_results = 1000
        objects: list[SavingsPlan] = []
        pager = None
        client = self._session.client(
            'savingsplans', region_name=self._session.region_name)

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

    async def collect_resources(
        self,
        resources_to_fetch: Iterable[SupportedResource],
    ) -> list[Expiriable]:
        resource_futures: list[Coroutine] = []

        for resource_descr in resources_to_fetch:
            match resource_descr:
                case SupportedResource.COMPUTE_SAVINGS_PLAN:
                    resource_futures.append(
                        cast(Coroutine, self._list_savings_plans()))

                case SupportedResource.DYNAMODB_RESERVED_CAPACITY:
                    resource_futures.append(
                        cast(Coroutine, self._list_dynamodb_reserved_capacities()))

        resources: Iterable[Expiriable] = itertools.chain.from_iterable(
            await asyncio.gather(*resource_futures),
        )

        # collect eagerly - so not to return an async generator
        return list(filter(
            lambda r: r.id not in self._ignored_uuids,
            resources,
        ))

    def ignore_uuids(self, ignored_uuids: Iterable[str]):
        self._ignored_uuids.update(ignored_uuids)

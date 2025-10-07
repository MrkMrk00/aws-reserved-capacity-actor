import dataclasses
import datetime
import json

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


@dataclasses.dataclass
class ReservedCapacity:
    DurationSeconds: int
    FixedPrice: float
    InstanceCount: int
    ReservedCapacityId: str
    ReservedCapacityState: str
    StartDate: str
    UsagePrice: float
    UsageType: str

    def is_active(self) -> bool:
        return self.ReservedCapacityState == 'active'

    def start_date(self) -> datetime.datetime:
        unix_timestamp = int(self.StartDate) / 1000

        return datetime.datetime.fromtimestamp(unix_timestamp)

    def valid_until(self) -> datetime.datetime:
        valid_delta = datetime.timedelta(seconds=int(self.DurationSeconds))

        return self.start_date() + valid_delta

    def upfront_cost(self):
        return int(self.FixedPrice) * self.InstanceCount

    @classmethod
    def from_dict(cls, dct: dict):
        # unsure no extra fields in dct
        fields = {field.name for field in dataclasses.fields(cls)}
        data = {k: v for k, v in dct.items() if k in fields}

        return cls(**data)


_RPC_RESERVED_CAPACITY = 'ReservedCapacity_20120810.DescribeReservedCapacity'


def _make_request(
    session: boto3.Session,
    region: str,
    service: str,
    rpc_target: str,
    api_identification: tuple[str, str],
    method: str = 'POST',
    body: dict = {},
):
    credentials = session.get_credentials().get_frozen_credentials()

    url = f'https://{service}.{region}.amazonaws.com/'
    headers = {
        'Host': f'{service}.{region}.amazonaws.com',
        'Content-Type': 'application/x-amz-json-1.0',
        'X-Amz-Target': rpc_target,
        'X-Amz-User-Agent': f'aws-sdk-js/1.0.0 os/macOS/10.15 lang/js md/browser/Firefox_144.0 api/{api_identification[0]}/{api_identification[1]}',
    }
    body = json.dumps(body).encode()

    request = AWSRequest(method=method, url=url,
                         data=body, headers=headers)

    SigV4Auth(credentials, service_name=service,
              region_name=region).add_auth(request)

    prepared_headers = dict(request.headers.items())

    response = requests.request(
        method, url, headers=prepared_headers, data=body)

    return response


def list_dynamodb_reserved_capacities(
    session: boto3.Session,
    region: str,
) -> list[ReservedCapacity]:
    objects = []

    start_key = 0
    while True:
        response = _make_request(
            session,
            region,
            'dynamodb',
            _RPC_RESERVED_CAPACITY,
            ('dynamodbreservedcapacity', '1.0.0'),
            body={'ExclusiveStartKey': str(start_key)},
        )
        assert response.status_code == 200

        body = response.json()
        objects.extend(ReservedCapacity.from_dict(json_capacity)
                       for json_capacity in body.get('ReservedCapacities'))

        next_pager = int(body.get('LastEvaluatedKey'))

        # no more items to fetch
        if next_pager - start_key > len(body.get('ReservedCapacities')):
            break
        else:
            start_key = next_pager

    return objects

import dataclasses
import json
import pprint

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

ORG_REGION = 'us-east-1'


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


class CustomAwsClient:
    RPC_RESERVED_CAPACITY = 'ReservedCapacity_20120810.DescribeReservedCapacity'

    def __init__(
            self,
            session: boto3.Session,
            region: str
    ):
        self._session = session
        self._region = region

    def _make_request(
            self,
            service: str,
            rpc_target: str,
            body: dict,
            method: str = 'POST',
    ) -> requests.Response:
        credentials = self._session.get_credentials().get_frozen_credentials()

        url = f'https://{service}.{self._region}.amazonaws.com/'
        headers = {
            'Host': f'{service}.{self._region}.amazonaws.com',
            'Content-Type': 'application/x-amz-json-1.0',
            'X-Amz-Target': rpc_target,
            'X-Amz-User-Agent': 'aws-sdk-js/1.0.0 os/macOS/10.15 lang/js md/browser/Firefox_144.0 api/dynamodbreservedcapacity/1.0.0',
        }
        body = json.dumps(body).encode()

        request = AWSRequest(method=method, url=url,
                             data=body, headers=headers)

        SigV4Auth(credentials, service_name=service,
                  region_name=self._region).add_auth(request)

        prepared_headers = dict(request.headers.items())

        response = requests.request(
            method, url, headers=prepared_headers, data=body)

        return response

    def dynamodb_reserved_capacities(self) -> list[ReservedCapacity]:
        objects = []

        start_key = 0
        while True:
            response = self._make_request('dynamodb', self.RPC_RESERVED_CAPACITY, {
                'ExclusiveStartKey': str(start_key)})
            assert response.status_code == 200

            body = response.json()
            objects.extend(ReservedCapacity(**json_capacity)
                           for json_capacity in body.get('ReservedCapacities'))

            next_pager = int(body.get('LastEvaluatedKey'))

            # no more items to fetch
            if next_pager - start_key > len(body.get('ReservedCapacities')):
                break
            else:
                start_key = next_pager

        return objects


def main() -> int:
    client = CustomAwsClient(boto3.Session(), ORG_REGION)
    result = client.dynamodb_reserved_capacities()
    pprint.pprint(result)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())

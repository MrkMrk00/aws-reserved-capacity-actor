import pprint

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

ORG_REGION = 'us-east-1'


class CustomAwsClient:
    RESERVED_CAPACITY = 'ReservedCapacity_20120810.DescribeReservedCapacity'

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
        url = f'https://{service}.{self._region}.amazonaws.com/'
        headers = {
            'Host': f'{service}.{self._region}.amazonaws.com',
            'Content-Type': 'application/x-amz-json-1.0',
            'X-Amz-Target': rpc_target,
            'X-Amz-User-Agent': 'aws-sdk-js/1.0.0 os/macOS/10.15 lang/js md/browser/Firefox_144.0 api/dynamodbreservedcapacity/1.0.0',
        }

        request = AWSRequest(method=method, url=url,
                             data=body, headers=headers)
        creds = self._session.get_credentials().get_frozen_credentials()

        SigV4Auth(creds, service_name=service,
                  region_name=self._region).add_auth(request)

        prepared_headers = dict(request.headers.items())
        pprint.pprint(prepared_headers)

        return requests.request(
            method, url, headers=prepared_headers, data=body)

    def get_dynamodb_reserved_capacity(self):
        pprint.pprint(self._make_request(
            'dynamodb', self.RESERVED_CAPACITY, {}))


def main() -> int:
    client = CustomAwsClient(boto3.Session(), ORG_REGION)
    client.get_dynamodb_reserved_capacity()

    return 0


if __name__ == '__main__':
    raise SystemExit(main())

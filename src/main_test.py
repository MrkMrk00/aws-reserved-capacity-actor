import datetime
import math
import unittest
from typing import cast

from .aws import ReservedCapacity
from .notifications import get_expiring_soon


def _create_test_reserved_capacity(id: str, expire_date: datetime.datetime):
    start_date = datetime.datetime.now() - datetime.timedelta(days=14)

    return ReservedCapacity(
        FixedPrice=2.0,
        InstanceCount=2,
        StartDate=str(math.trunc(start_date.timestamp() * 1000)),
        ReservedCapacityId=id,
        ReservedCapacityState='active',
        UsageType='test',
        UsagePrice=0,
        DurationSeconds=int((expire_date - start_date).total_seconds())
    )


class ExpiringTimingTestCase(unittest.TestCase):
    def test_does_not_fire_too_early(self):
        notify_delta = datetime.timedelta(days=3)
        should_not_notify_time = (
            datetime.datetime.now()
            + notify_delta
            + datetime.timedelta(days=1)
        )
        should_notify_time = (
            datetime.datetime.now()
            + notify_delta
            - datetime.timedelta(days=1)
        )

        _expiring_soon = list(get_expiring_soon([
            _create_test_reserved_capacity('0', should_not_notify_time),
            _create_test_reserved_capacity('1', should_notify_time),
        ], notify_delta))

        expiring_soon = cast(list[ReservedCapacity], _expiring_soon)

        self.assertEqual(len(expiring_soon), 1)
        self.assertEqual(expiring_soon[0].ReservedCapacityId, '1')

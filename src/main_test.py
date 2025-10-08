import datetime
import math
import unittest

from apify import Actor
from crawlee.storages import KeyValueStore

from .aws import ReservedCapacity
from .main import SENT_NOTIFICATIONS_KEY, cleanup_kv_store, get_expiring_soon


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

        expiring_soon = list(get_expiring_soon([
            _create_test_reserved_capacity('0', should_not_notify_time),
            _create_test_reserved_capacity('1', should_notify_time),
        ], notify_delta))

        self.assertEqual(len(expiring_soon), 1)
        self.assertEqual(expiring_soon[0].ReservedCapacityId, '1')


class KVStoreCleanupTestCase(unittest.IsolatedAsyncioTestCase):
    actor: Actor

    async def asyncSetUp(self):
        self.actor = Actor(exit_process=False)
        await self.actor.init()

    async def asyncTearDown(self):
        await self.actor.exit()

    async def test_deletes_old_data_from_kv_store(self):
        rcs = [
            _create_test_reserved_capacity('0', datetime.datetime.now()),
            _create_test_reserved_capacity('1', datetime.datetime.now()),
        ]

        store: KeyValueStore = await self.actor.open_key_value_store(name='test_store')
        await store.set_value(SENT_NOTIFICATIONS_KEY, [r.id for r in rcs])

        self.assertEqual(
            await store.get_value(SENT_NOTIFICATIONS_KEY),
            [rcs[0].id, rcs[1].id],
        )

        rcs.pop()
        await cleanup_kv_store(store, rcs)

        self.assertEqual(await store.get_value(SENT_NOTIFICATIONS_KEY), [rcs[0].id])

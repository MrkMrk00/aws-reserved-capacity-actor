import asyncio
import datetime
import enum
from pprint import pprint
from typing import Generator, Iterable

import slack_sdk
from crawlee.storages import KeyValueStore

from .aws import Expiriable

_SENT_NOTIFICATIONS_KEY = 'notifications-sent'


def acache(async_func):
    """
    ignores parameters!!!
    """
    previous_value = None

    async def _decorated(*args, **kwargs):
        nonlocal previous_value
        if previous_value is None:
            previous_value = await async_func(*args, **kwargs)

        return previous_value

    return _decorated


def _format_resource_row(
        resource: Expiriable,
        owner_slack_id: str | None,
        bolden: bool = False,
) -> str:
    now = datetime.datetime.now().astimezone()
    expiring_in = (resource.valid_until() - now).days
    bought_date = resource.start_date().strftime('%Y-%m-%d')

    text = resource.describe()
    text += ' (expiring in '

    if bolden:
        text += f'**{expiring_in}**'
    else:
        text += str(expiring_in)

    text += f' days - bought: {bought_date}) '
    if owner_slack_id is not None:
        text += f' <@{owner_slack_id}> '
    text += f'([link]({resource.get_link()}))'

    return text


class Notification(enum.StrEnum):
    URGENT = enum.auto()          # spam every day    (default 7 days)
    REMINDER_SHORT = enum.auto()  # short time period (default 14 days)
    REMINDER_LONG = enum.auto()   # long time period  (default 1 month)

    def notify_delta(self, actor_input: dict) -> datetime.timedelta:
        days = actor_input.get(f'days_{str(self)}')
        assert days is not None, 'Malformed Actor INPUT'

        return datetime.timedelta(days=days)

    @property
    def store_key(self):
        return f'{_SENT_NOTIFICATIONS_KEY}-{str(self)}'


@acache
async def _fetch_slack_users(slack: slack_sdk.WebClient):
    return await asyncio.to_thread(slack.users_list)


async def _get_slack_id_for_email(slack: slack_sdk.WebClient, email: str) -> str | None:
    slack_users = await _fetch_slack_users(slack)
    members = slack_users.get('members')

    for member in members:
        member_email = member.get('profile', {}).get('email')

        if member_email == email:
            return member['id']

    # not found
    return None


async def create_notification_text(
    notification: Notification,
    slack: slack_sdk.WebClient,
    resources: list[Expiriable],
    default_owner: str | None,
) -> str:
    message: str
    match notification:
        case Notification.URGENT:
            message = 'Hey!\n'
            message += 'These AWS savings plans will be expiring very soon! You might want to renew them.\n\n'  # noqa: E501
        case _:
            message = 'Hi.\n'
            message += 'There seem to be some savings plans in AWS that will be expiring soon. Just letting you know ;)\n\n'  # noqa: E501

    for resource in resources:
        owner_email = resource.owner or default_owner
        owner = None

        if owner_email is not None:
            owner = await _get_slack_id_for_email(slack, owner_email)

        message += f'- {_format_resource_row(resource, owner, bolden=notification is Notification.URGENT)}\n'  # noqa: E501

    return message


def get_expiring_soon(
        capacities: Iterable[Expiriable],
        notify_period: datetime.timedelta,
        ignore_ids: set[str] = set(),
) -> Generator[Expiriable]:
    for capacity in capacities:
        now = datetime.datetime.now().astimezone()
        valid_until = capacity.valid_until()

        if (not capacity.is_active()
                or valid_until < now
                or capacity.id in ignore_ids):
            continue

        #                V(now+notify_period)
        # ---|--------|--|-----
        #    ^now     ^valid_until

        if valid_until <= now + notify_period:
            yield capacity


async def mark_resources_as_notified(
        notification_type: Notification,
        store: KeyValueStore,
        resources: Iterable[Expiriable],
) -> None:
    if notification_type is Notification.URGENT:
        return

    previous_ids: set[str] = set(await store.get_value(notification_type.store_key, []))
    previous_ids.update(r.id for r in resources)

    await store.set_value(notification_type.store_key, list(previous_ids))


async def cleanup_kv_store(
        notification_type: Notification,
        store: KeyValueStore,
        all_savings_plans: Iterable[Expiriable],
) -> None:
    savings_plans_ids = {sp.id for sp in all_savings_plans}
    saved_keys: set[str] = set(await store.get_value(notification_type.store_key, []))

    only_existing_keys = saved_keys.intersection(savings_plans_ids)

    await store.set_value(notification_type.store_key, list(only_existing_keys))

"""Typed resource inventory and canonical minimum-pack selection policy."""

from __future__ import annotations

from dataclasses import dataclass


_RESOURCE_ORDER = ("food", "wood", "iron", "gold")


@dataclass(frozen=True, slots=True)
class ResourceItem:
    """Identifies an existing resource pack and its freshly observed owned count."""

    item_id: str
    resource: str
    amount: int
    owned: int
    fingerprint: str

    def __post_init__(self) -> None:
        """Rejects unsupported resources and incomplete semantic evidence."""

        if self.resource not in _RESOURCE_ORDER:
            raise ValueError("Unsupported resource pack.")
        if not self.item_id or not self.fingerprint:
            raise ValueError("Resource pack requires an identity and fresh fingerprint.")
        if type(self.amount) is not int or self.amount <= 0:
            raise ValueError("Resource amount must be a positive integer.")
        if type(self.owned) is not int or self.owned < 0:
            raise ValueError("Resource owned count must be a non-negative integer.")

    @property
    def identity(self) -> tuple[str, str, int]:
        """Returns stable semantic identity independently of changing owned count."""

        return self.item_id, self.resource, self.amount


@dataclass(frozen=True, slots=True)
class ResourceInventory:
    """Carries a bounded full-list scan rather than only the visible viewport."""

    items: tuple[ResourceItem, ...]
    exhausted: bool
    artifact_paths: tuple[str, ...]


def smallest_resource_item(inventory: ResourceInventory) -> ResourceItem | None:
    """Chooses the global smallest owned pack, with Food/Wood/Iron/Gold ties."""

    if not inventory.exhausted or not inventory.artifact_paths:
        raise ValueError("Resource selection requires an evidenced full inventory scan.")
    identities = [item.identity for item in inventory.items]
    if len(set(identities)) != len(identities):
        raise ValueError("Inventory scan contains duplicate item identities.")
    owned = tuple(item for item in inventory.items if item.owned > 0)
    if not owned:
        return None
    return min(owned, key=lambda item: (item.amount, _RESOURCE_ORDER.index(item.resource), item.item_id))

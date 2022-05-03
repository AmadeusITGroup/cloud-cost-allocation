# coding: utf-8

from abc import ABC, abstractmethod
from configparser import ConfigParser

from cloud_cost_allocation.cloud_cost_allocator import CostItemFactory, CostItem


class GenericReader(ABC):
    """
    Reads Azure Enterprise Agreement amortized cloud costs
    """

    __slots__ = (
        'config',             # type: ConfigParser
        'cost_item_factory',  # type: cloud_cost_allocator.CostItemFactory
    )

    def __init__(self, cost_item_factory: CostItemFactory, config: ConfigParser):
        self.config = config
        self.cost_item_factory = cost_item_factory

    def read(self, cost_items, data) -> None:
        # Read cost lines
        for item in data:
            cost_item = self.read_item(item)
            if cost_item:
                # Add cloud cost item
                cost_items.append(cost_item)

    @abstractmethod
    def read_item(self, item) -> CostItem:
        pass

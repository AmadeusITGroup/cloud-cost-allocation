# coding: utf-8

from abc import ABC, abstractmethod

from cloud_cost_allocation.cloud_cost_allocator import CostItemFactory, CostItem


class GenericReader(ABC):
    """
    Base class for readers
    """

    __slots__ = (
        'cost_item_factory',  # type: CostItemFactory
    )

    def __init__(self, cost_item_factory: CostItemFactory):
        self.cost_item_factory = cost_item_factory

    def read(self, cost_items, data) -> None:
        # Read cost lines
        for item in data:
            cost_item = self.read_item(item)
            if cost_item:
                # Add cloud cost item
                cost_items.append(cost_item)

    def fill_from_tags(self, cost_item) -> None:

        # Get config
        config = self.cost_item_factory.config

        # Service
        for service_tag_key in config.service_tag_keys:
            if service_tag_key in cost_item.tags:
                cost_item.service = cost_item.tags[service_tag_key].strip().lower()
                break

        # Instance
        for instance_tag_key in config.instance_tag_keys:
            if instance_tag_key in cost_item.tags:
                cost_item.instance = cost_item.tags[instance_tag_key].strip().lower()
                break

        # Dimensions
        for dimension, dimension_tag_keys in config.dimension_tag_keys.items():
            for dimension_tag_key in dimension_tag_keys:
                if dimension_tag_key in cost_item.tags:
                    cost_item.dimensions[dimension] = cost_item.tags[dimension_tag_key].strip().lower()
                    break

    @abstractmethod
    def read_item(self, item) -> CostItem:
        pass

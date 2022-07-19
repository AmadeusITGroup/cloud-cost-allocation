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

    def fill_from_tags(self, cost_item) -> None:
        # Service
        for service_tag_key in self.config['TagKey']['Service'].split(","):
            service_tag_key = service_tag_key.strip()
            if service_tag_key in cost_item.tags:
                cost_item.service = cost_item.tags[service_tag_key].strip().lower()
                break

        # Instance
        if 'Instance' in self.config['TagKey']:
            for instance_tag_key in self.config['TagKey']['Instance'].split(","):
                instance_tag_key = instance_tag_key.strip()
                if instance_tag_key in cost_item.tags:
                    cost_item.instance = cost_item.tags[instance_tag_key].strip().lower()
                    break

        # Dimensions
        if 'Dimensions' in self.config['General']:
            for dimension in self.config['General']['Dimensions'].split(","):
                dimension = dimension.strip()
                for dimension_tag_key in self.config['TagKey'][dimension].split(","):
                    dimension_tag_key = dimension_tag_key.strip()
                    if dimension_tag_key in cost_item.tags:
                        cost_item.dimensions[dimension] = cost_item.tags[dimension_tag_key].strip().lower()
                        break

    @abstractmethod
    def read_item(self, item) -> CostItem:
        pass

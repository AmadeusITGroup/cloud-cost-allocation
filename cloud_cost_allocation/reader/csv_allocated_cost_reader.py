# coding: utf-8

from logging import error
import re

from cloud_cost_allocation.cost_items import CloudCostItem, ConsumerCostItem, CostItem, CostItemFactory
from cloud_cost_allocation.reader.base_reader import GenericReader
from cloud_cost_allocation.utils import utils


class CSV_AllocatedCostReader(GenericReader):
    """
    Reads cost items from a previous allocation
    """

    def __init__(self, cost_item_factory: CostItemFactory):
        super().__init__(cost_item_factory)

    def initialize_cost_item(self, cost_item: CostItem, line):

        # Date
        cost_item.date_str = line['Date']

        # Service
        cost_item.service = line['Service']

        # Instance
        cost_item.instance = line['Instance']

        # Dimensions
        config = self.cost_item_factory.config
        for dimension in config.dimensions:
            cost_item.dimensions[dimension] = line[dimension]
        tag_str = line["Tags"]
        if tag_str:
            cost_item.tags = utils.deserialize_tags(tag_str)

        # Amounts
        index = 0
        for amount in config.amounts:
            if amount in line:
                amount_value_str = line[amount]
                if amount_value_str:
                    cost_item.amounts[index] = float(amount_value_str)
            index += 1

        # Currency
        cost_item.currency = line['Currency']

    def read_cloud_cost_item(self, line) -> CloudCostItem:
        cloud_cost_item = self.cost_item_factory.create_cloud_cost_item()
        self.initialize_cost_item(cloud_cost_item, line)
        return cloud_cost_item

    def read_consumer_cost_item(self, line) -> ConsumerCostItem:

        # Create and initialize consumer cost item
        consumer_cost_item = self.cost_item_factory.create_consumer_cost_item()
        self.initialize_cost_item(consumer_cost_item, line)

        # Provider service
        consumer_cost_item.provider_service = line["ProviderService"]

        # Provider instance
        consumer_cost_item.provider_instance = line["ProviderInstance"]

        # Provider tag selector
        consumer_cost_item.provider_tag_selector = line["ProviderTagSelector"]

        # Provider cost allocation type
        consumer_cost_item.provider_cost_allocation_type = line["ProviderCostAllocationType"]

        # Allocation keys
        config = self.cost_item_factory.config
        index = 0
        for allocation_key in config.allocation_keys:
            if allocation_key in line:
                allocation_key_value_str = line[allocation_key]
                if allocation_key_value_str:
                    consumer_cost_item.allocation_keys[index] = float(allocation_key_value_str)
            index += 1

        # Provider cost allocation cloud tag selector
        consumer_cost_item.provider_cost_allocation_cloud_tag_selector = line["ProviderCostAllocationCloudTagSelector"]

        # Provider meters
        if config.nb_provider_meters:
            for i in range(1, config.nb_provider_meters + 1):
                provider_meter = {
                    "Name": line['ProviderMeterName%s' % i],
                    "Unit": line['ProviderMeterUnit%s' % i],
                    "Value": line['ProviderMeterValue%s' % i],
                }
                consumer_cost_item.provider_meters[i-1] = provider_meter

        # Product
        consumer_cost_item.product = line["Product"]

        # Product dimensions
        if config.nb_product_dimensions:
            for i in range(1, config.nb_product_dimensions+1):
                product_dimension = {
                    "Name": line['ProductDimensionName%s' % i],
                    "Element": line['ProductDimensionElement%s' % i]
                }
                consumer_cost_item.product_dimensions[i-1] = product_dimension

        # Product meters
        if config.nb_product_meters:
            product_meter0 = {
                "Name": line['ProductMeterName'],
                "Unit": line['ProductMeterUnit'],
                "Value": line['ProductMeterValue'],
            }
            consumer_cost_item.product_meters[0] = product_meter0
        if config.nb_product_meters > 1:
            for i in range(2, config.nb_product_meters + 1):
                product_meter = {
                    "Name": line['ProductMeterName%s' % i],
                    "Unit": line['ProductMeterUnit%s' % i],
                    "Value": line['ProductMeterValue%s' % i],
                }
                consumer_cost_item.product_meters[i-1] = product_meter

        # Product amounts
        index = 0
        for amount in config.amounts:
            product_amount = 'Product' + amount
            if product_amount in line:
                product_amount_value_str = line[product_amount]
                if product_amount_value_str:
                    consumer_cost_item.product_amounts[index] = float(product_amount_value_str)
            index += 1

        return consumer_cost_item

    def read_item(self, line) -> CostItem:
        if line['ProviderService']:
            return self.read_consumer_cost_item(line)
        else:
            return self.read_cloud_cost_item(line)

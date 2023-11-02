'''
Created on 20.04.2022

@author: marc.diensberg
'''

from logging import error
import re

from cloud_cost_allocation.cost_items import ConsumerCostItem, CostItemFactory
from cloud_cost_allocation.reader.base_reader import GenericReader
from cloud_cost_allocation.utils import utils


class CSV_CostAllocationKeysReader(GenericReader):
    '''
    classdocs
    '''

    def __init__(self, cost_item_factory: CostItemFactory):
        super().__init__(cost_item_factory)

    def read_item(self, line) -> ConsumerCostItem:

        # Create consumer cost item
        consumer_cost_item = self.cost_item_factory.create_consumer_cost_item()

        # Provider service amd instance
        consumer_cost_item.date_str = line['Date'].strip()
        if 'ProviderService' in line:
            consumer_cost_item.provider_service = line['ProviderService'].lower()
        if not consumer_cost_item.provider_service:
            error("Skipping cost allocation key line without ProviderService")
            return None

        # Provider instance
        if 'ProviderInstance' in line:
            consumer_cost_item.provider_instance = line['ProviderInstance'].lower()
        if not consumer_cost_item.provider_instance:
            consumer_cost_item.provider_instance = consumer_cost_item.provider_service  # Default

        # Provider tag selector
        if "ProviderTagSelector" in line:
            consumer_cost_item.provider_tag_selector = line["ProviderTagSelector"].lower()

        # Provider cost allocation type and related fields
        consumer_cost_item.provider_cost_allocation_type = "Key"  # Default value
        if 'ProviderCostAllocationType' in line:
            consumer_cost_item.provider_cost_allocation_type = line['ProviderCostAllocationType']
            if consumer_cost_item.provider_cost_allocation_type not in ("Key", "Cost", "CloudTagSelector"):
                error("Unknown ProviderCostAllocationType '" + consumer_cost_item.provider_cost_allocation_type +
                      "' for ProviderService '" + consumer_cost_item.provider_service + "'")
                return None
        if consumer_cost_item.provider_cost_allocation_type == 'Key':
            if 'ProviderCostAllocationKey' in line:
                key_str = line['ProviderCostAllocationKey']
                if utils.is_float(key_str):
                    consumer_cost_item.allocation_keys[0] = float(key_str)
            if consumer_cost_item.allocation_keys[0] == 0.0:
                error("Skipping cost allocation key line with non-float " +
                      " ProviderCostAllocationKey: '" + key_str + "'" +
                      " for ProviderService '" + consumer_cost_item.provider_service + "'")
                return None
        elif consumer_cost_item.provider_cost_allocation_type == "CloudTagSelector":
            if 'ProviderCostAllocationCloudTagSelector' in line:
                consumer_cost_item.provider_cost_allocation_cloud_tag_selector = \
                    line['ProviderCostAllocationCloudTagSelector']

        # Further allocation keys
        config = self.cost_item_factory.config
        if config.nb_allocation_keys > 1:
            key_index = 1
            for further_allocation_key in config.allocation_keys[1:]:
                if further_allocation_key in line and line[further_allocation_key]:
                    key_str = line[further_allocation_key]
                    if utils.is_float(key_str):
                        consumer_cost_item.allocation_keys[key_index] = float(key_str)
                key_index += 1

        # Provider meters
        if config.nb_provider_meters:
            for i in range(1, config.nb_provider_meters + 1):
                provider_meter_name = None
                provider_meter_unit = None
                provider_meter_value = None
                if 'ProviderMeterName%d' % i in line:
                    provider_meter_name = line['ProviderMeterName%d' % i].lower()
                if 'ProviderMeterUnit%d' % i in line:
                    provider_meter_unit = line['ProviderMeterUnit%d' % i].lower()
                if 'ProviderMeterValue%d' % i in line:
                    provider_meter_value_column = 'ProviderMeterValue%d' % i
                    provider_meter_value = line[provider_meter_value_column]
                    if provider_meter_value and not utils.is_float(provider_meter_value):
                        error("Value '" + provider_meter_value + "' of '" + provider_meter_value_column +
                              "' of ProviderService '" + consumer_cost_item.provider_service + "'" +
                              "is not a float")
                        provider_meter_value = None
                if provider_meter_name or provider_meter_unit or provider_meter_value:
                    provider_meter = {
                        'Name': provider_meter_name,
                        'Unit': provider_meter_unit,
                        'Value': provider_meter_value,
                    }
                    consumer_cost_item.provider_meters[i-1] = provider_meter

        # Consumer tags
        if 'ConsumerTags' in line:
            consumer_tags = line["ConsumerTags"]
            if consumer_tags:
                consumer_cost_item.tags = utils.deserialize_tags(consumer_tags)

        # Populate consumer cost item info from consumer tags
        # Note: if both consumer tags and other consumer columns (ConsumerService, ConsumerInstance,
        # Consumer<Dimensions>) are populated with overlapping info, then info from other consumer columns takes
        # precedence over info from consumer tags (other consumer columns will be processed after consumer tags)
        self.fill_from_tags(consumer_cost_item)

        # Populate/overwrite consumer cost item info from explicit consumer columns if set
        if 'ConsumerService' in line and line['ConsumerService']:
            consumer_cost_item.service = line['ConsumerService'].lower()
        if 'ConsumerInstance' in line and line['ConsumerInstance']:
            consumer_cost_item.instance = line['ConsumerInstance'].lower()
        for dimension in config.dimensions:
            consumer_dimension = 'Consumer' + dimension
            if consumer_dimension in line and line[consumer_dimension]:
                consumer_cost_item.dimensions[dimension] = line[consumer_dimension].lower()

        # Product
        if 'Product' in line:
            consumer_cost_item.product = line['Product'].lower()

        # Product dimensions
        if config.nb_product_dimensions:
            for i in range(1, config.nb_product_dimensions + 1):
                product_dimension_name_column = "ProductDimensionName%d" % i
                if product_dimension_name_column in line:
                    product_dimension_name = line[product_dimension_name_column].lower()
                else:
                    product_dimension_name = None
                product_dimension_element_column = "ProductDimensionElement%d" % i
                if product_dimension_element_column in line:
                    product_dimension_element = line[product_dimension_element_column].lower()
                else:
                    product_dimension_element = None
                if product_dimension_name or product_dimension_element:
                    product_dimension = {
                        'Name': product_dimension_name,
                        'Element': product_dimension_element,
                    }
                    consumer_cost_item.product_dimensions[i-1] = product_dimension

        # Product meters
        if config.nb_product_meters:
            for i in range(1, config.nb_product_meters + 1):
                product_meter_name_column = "ProductMeterName"
                if i > 1:
                    product_meter_name_column += str(i)
                if product_meter_name_column in line:
                    product_meter_name = line[product_meter_name_column].lower()
                else:
                    product_meter_name = None
                product_meter_unit_column = "ProductMeterUnit"
                if i > 1:
                    product_meter_unit_column += str(i)
                if product_meter_unit_column in line:
                    product_meter_unit = line[product_meter_unit_column].lower()
                else:
                    product_meter_unit = None
                product_meter_value = None
                product_meter_value_column = "ProductMeterValue"
                if i > 1:
                    product_meter_value_column += str(i)
                if product_meter_value_column in line:
                    product_meter_value = line[product_meter_value_column]
                    if product_meter_value and not utils.is_float(product_meter_value):
                        error("Value '" + product_meter_value + "' of '" + product_meter_value_column +
                              "' of ProviderService '" + consumer_cost_item.provider_service + "' " +
                              "is not a float")
                        product_meter_value = None
                if product_meter_name or product_meter_unit or product_meter_value:
                    product_meter = {
                        'Name': product_meter_name,
                        'Unit': product_meter_unit,
                        'Value': product_meter_value,
                    }
                    consumer_cost_item.product_meters[i-1] = product_meter

        # Set default values for service and instance
        if not consumer_cost_item.service:
            if consumer_cost_item.product:  # Product exists: let's consider it's final consumption
                consumer_cost_item.service = consumer_cost_item.provider_service
                consumer_cost_item.instance = consumer_cost_item.provider_instance
            else:  # No product, no consumer service: consumer is default service
                consumer_cost_item.service = config.default_service
                consumer_cost_item.instance = consumer_cost_item.service
        elif not consumer_cost_item.instance:  # Same as service by default
            consumer_cost_item.instance = consumer_cost_item.service

        return consumer_cost_item

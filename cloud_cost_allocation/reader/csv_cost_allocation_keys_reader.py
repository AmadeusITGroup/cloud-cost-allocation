'''
Created on 20.04.2022

@author: marc.diensberg
'''

from configparser import ConfigParser
from logging import error
import re

from cloud_cost_allocation.cost_items import ConsumerCostItem, CostItemFactory
from cloud_cost_allocation.reader.base_reader import GenericReader


class CSV_CostAllocationKeysReader(GenericReader):
    '''
    classdocs
    '''

    __slots__ = (
        'nb_provider_meters',     # type: int
        'nb_product_dimensions',  # type: int
        'nb_product_meters',      # type: int
    )

    def __init__(self, cost_item_factory: CostItemFactory, config: ConfigParser):
        '''
        Constructor
        '''
        super().__init__(cost_item_factory, config)
        if 'NumberOfProviderMeters' in self.config['General']:
            self.nb_provider_meters = int(self.config['General']['NumberOfProviderMeters'])
        else:
            self.nb_provider_meters = 0
        if 'NumberOfProductDimensions' in self.config['General']:
            self.nb_product_dimensions = int(self.config['General']['NumberOfProductDimensions'])
        else:
            self.nb_product_dimensions = 0
        if 'NumberOfProductMeters' in self.config['General']:
            self.nb_product_meters = int(self.config['General']['NumberOfProductMeters'])
        else:
            self.nb_product_meters = 0

    def read_item(self, line) -> ConsumerCostItem:
        # Create item
        consumer_cost_item = self.cost_item_factory.create_consumer_cost_item()

        # Populate provider service amd instance info
        consumer_cost_item.date_str = line['Date'].strip()
        if 'ProviderService' in line:
            consumer_cost_item.provider_service = line['ProviderService'].lower()
        if not consumer_cost_item.provider_service:
            error("Skipping cost allocation key line without ProviderService")
            return None
        if 'ProviderInstance' in line:
            consumer_cost_item.provider_instance = line['ProviderInstance'].lower()
        if not consumer_cost_item.provider_instance:
            consumer_cost_item.provider_instance = consumer_cost_item.provider_service  # Default value
        consumer_cost_item.provider_cost_allocation_type = "Key"  # Default value
        if 'ProviderCostAllocationType' in line:
            consumer_cost_item.provider_cost_allocation_type = line['ProviderCostAllocationType']
            if consumer_cost_item.provider_cost_allocation_type not in ("Key", "Cost", "CloudTagSelector"):
                error("Unknown ProviderCostAllocationType '" + consumer_cost_item.provider_cost_allocation_type +
                      "' for ProviderService '" + consumer_cost_item.provider_service + "'")
                return None

        # Populate provider tag selector and cost allocation type
        if "ProviderTagSelector" in line:
            consumer_cost_item.provider_tag_selector = line["ProviderTagSelector"].lower()
        if consumer_cost_item.provider_cost_allocation_type == 'Key':
            key_str = ""
            if 'ProviderCostAllocationKey' in line and line['ProviderCostAllocationKey']:
                try:
                    key_str = line['ProviderCostAllocationKey']
                    consumer_cost_item.provider_cost_allocation_key = float(key_str)
                except (TypeError, ValueError):
                    pass
            if consumer_cost_item.provider_cost_allocation_key == 0.0:
                error("Skipping cost allocation key line with non-float " +
                      " ProviderCostAllocationKey: '" + key_str + "'" +
                      " for ProviderService '" + consumer_cost_item.provider_service + "'")
                return None
        elif consumer_cost_item.provider_cost_allocation_type == "CloudTagSelector":
            if 'ProviderCostAllocationCloudTagSelector' in line:
                consumer_cost_item.provider_cost_allocation_cloud_tag_selector = \
                    line['ProviderCostAllocationCloudTagSelector']

        # Populate provider meters
        if self.nb_provider_meters:
            for i in range(1, self.nb_provider_meters + 1):
                provider_meter_name = None
                provider_meter_unit = None
                provider_meter_value = None
                if 'ProviderMeterName%d' % i in line:
                    provider_meter_name = line['ProviderMeterName%d' % i]
                if 'ProviderMeterUnit%d' % i in line:
                    provider_meter_unit = line['ProviderMeterUnit%d' % i]
                if 'ProviderMeterValue%d' % i in line:
                    provider_meter_value_column = 'ProviderMeterValue%d' % i
                    provider_meter_value = line[provider_meter_value_column]
                    if provider_meter_value:
                        try:
                            float(provider_meter_value)
                        except (TypeError, ValueError):
                            error("Value '" + provider_meter_value + "' of '" + provider_meter_value_column +
                                  "' of ProviderService '" + consumer_cost_item.provider_service + "'" +
                                  "is not a float")
                            provider_meter_value = None
                if provider_meter_name or provider_meter_unit or provider_meter_value:
                    provider_meter = {}
                    provider_meter['Name'] = provider_meter_name
                    provider_meter['Unit'] = provider_meter_unit
                    provider_meter['Value'] = provider_meter_value
                    consumer_cost_item.provider_meters.append(provider_meter)

        # Populate tags from consumer tags
        if 'ConsumerTags' in line:
            consumer_tags = line["ConsumerTags"]
            if consumer_tags:
                tags = consumer_tags.split(',')
                for tag in tags:
                    if tag:
                        key_value_match = re.match("([^:]+):([^:]*)", tag)
                        if key_value_match:
                            key = key_value_match.group(1).strip().lower()
                            value = key_value_match.group(2).strip().lower()
                            consumer_cost_item.tags[key] = value
                        else:
                            error("Unexpected consumer tag format: '" + tag + "'")

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
        if 'Dimensions' in self.config['General']:
            for dimension in self.config['General']['Dimensions'].split(','):
                consumer_dimension = 'Consumer' + dimension.strip()
                if consumer_dimension in line and line[consumer_dimension]:
                    consumer_cost_item.dimensions[dimension] = line[consumer_dimension].lower()

        # Populate product
        if 'Product' in line:
            consumer_cost_item.product = line['Product'].lower()

        # Populate product dimensions
        if self.nb_product_dimensions:
            for i in range(1, self.nb_product_dimensions + 1):
                product_dimension_name_column = "ProductDimensionName%d" % i
                if product_dimension_name_column in line:
                    product_dimension_name = line[product_dimension_name_column]
                else:
                    product_dimension_name = None
                product_dimension_element_column = "ProductDimensionElement%d" % i
                if product_dimension_element_column in line:
                    product_dimension_element = line[product_dimension_element_column]
                else:
                    product_dimension_element = None
                if product_dimension_name or product_dimension_element:
                    product_dimension = {}
                    product_dimension['Name'] = product_dimension_name
                    product_dimension['Element'] = product_dimension_element
                    consumer_cost_item.product_dimensions.append(product_dimension)

        # Populate product meters
        if self.nb_product_meters:
            for i in range(1, self.nb_product_meters + 1):
                product_meter_name_column = "ProductMeterName"
                if i > 1:
                    product_meter_name_column += str(i)
                if product_meter_name_column in line:
                    product_meter_name = line[product_meter_name_column]
                else:
                    product_meter_name = None
                product_meter_unit_column = "ProductMeterUnit"
                if i > 1:
                    product_meter_unit_column += str(i)
                if product_meter_unit_column in line:
                    product_meter_unit = line[product_meter_unit_column]
                else:
                    product_meter_unit = None
                product_meter_value = None
                product_meter_value_column = "ProductMeterValue"
                if i > 1:
                    product_meter_value_column += str(i)
                if product_meter_value_column in line:
                    product_meter_value = line[product_meter_value_column]
                    if product_meter_value:
                        try:
                            float(product_meter_value)
                        except (TypeError, ValueError):
                            error("Value '" + product_meter_value + "' of '" + product_meter_value_column +
                                  "' of ProviderService '" + consumer_cost_item.provider_service + "'" +
                                  "is not a float")
                if product_meter_name or product_meter_unit or product_meter_value:
                    product_meter = {}
                    product_meter['Name'] = product_meter_name
                    product_meter['Unit'] = product_meter_unit
                    product_meter['Value'] = product_meter_value
                    consumer_cost_item.product_meters.append(product_meter)

        # Set default values for service and instance
        if not consumer_cost_item.service:
            if consumer_cost_item.product:  # Set self-consumption, to materialize final consumption
                consumer_cost_item.service = consumer_cost_item.provider_service
                consumer_cost_item.instance = consumer_cost_item.provider_instance
            else:  # Consumer is default service
                consumer_cost_item.service = self.config['General']['DefaultService'].strip()
                consumer_cost_item.instance = consumer_cost_item.service
        elif not consumer_cost_item.instance:  # Same as service by default
            consumer_cost_item.instance = consumer_cost_item.service

        return consumer_cost_item

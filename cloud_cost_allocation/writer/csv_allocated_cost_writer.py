'''
Created on 21.04.2022

@author: marc.diensberg
'''
from io import StringIO
from configparser import ConfigParser

from cloud_cost_allocation.cost_items import ServiceInstance
from cloud_cost_allocation.writer.base_writer import GenericWriter


class CSV_AllocatedCostWriter(GenericWriter):
    '''
    classdocs
    '''

    def __init__(self, service_instances: list[ServiceInstance], config: ConfigParser):
        super().__init__(service_instances, config)

    def get_headers(self) -> list[str]:
        headers = [
            'Date',
            'Service',
            'Instance',
            'Tags',
            'AmortizedCost',
            'OnDemandCost',
            'Currency',
            'ProviderService',
            'ProviderInstance',
            'ProviderTagSelector',
            'ProviderCostAllocationType',
            'ProviderCostAllocationKey',
            'ProviderCostAllocationCloudTagSelector',
            'Product',
            'ProductAmortizedCost',
            'ProductOnDemandCost'
        ]

        # Add dimensions
        if 'Dimensions' in self.config['General']:
            for dimension in self.config['General']['Dimensions'].split(","):
                headers.extend([dimension.strip()])

        # Add provider meters
        if 'NumberOfProviderMeters' in self.config['General']:
            for i in range(1, int(self.config['General']['NumberOfProviderMeters']) + 1):
                headers.extend(['ProviderMeterName%s' % i])
                headers.extend(['ProviderMeterUnit%s' % i])
                headers.extend(['ProviderMeterValue%s' % i])

        # Add product dimensions
        if 'NumberOfProductDimensions' in self.config['General']:
            for i in range(1, int(self.config['General']['NumberOfProductDimensions']) + 1):
                headers.extend(['ProductDimensionName%s' % i])
                headers.extend(['ProductDimensionElement%s' % i])

        # Add product meters
        if 'NumberOfProductMeters' in self.config['General']:
            for i in range(1, int(self.config['General']['NumberOfProductMeters']) + 1):
                if i == 1:
                    headers.extend(['ProductMeterName'])
                    headers.extend(['ProductMeterUnit'])
                    headers.extend(['ProductMeterValue'])
                else:
                    headers.extend(['ProductMeterName%s' % i])
                    headers.extend(['ProductMeterUnit%s' % i])
                    headers.extend(['ProductMeterValue%s' % i])

        return headers

    def export_item_base(self, cost_item, service_instance) -> dict[str]:
        data = {}
        # Add basic cost item data
        data['Date'] = cost_item.date_str
        data['Service'] = cost_item.service
        data['Instance'] = cost_item.instance
        tags_str = StringIO()
        for key, value in cost_item.tags.items():
            tags_str.write(key + ":" + value + ",")
        data['Tags'] = tags_str.getvalue()
        data['AmortizedCost'] = str(cost_item.amortized_cost)
        data['OnDemandCost'] = str(cost_item.on_demand_cost)
        data['Currency'] = cost_item.currency

        # Add dimensions
        for dimension_key, dimension_value in cost_item.dimensions.items():
            data[dimension_key] = dimension_value

        return data

    def export_item_consumer(self, cost_item, service_instance) -> dict[str]:
        data = self.export_item_base(cost_item, service_instance)
        # Add provider part
        data['ProviderService'] = cost_item.provider_service
        data['ProviderInstance'] = cost_item.provider_instance
        data['ProviderTagSelector'] = cost_item.provider_tag_selector
        data['ProviderCostAllocationType'] = cost_item.provider_cost_allocation_type
        data['ProviderCostAllocationKey'] = str(cost_item.provider_cost_allocation_key)
        data['ProviderCostAllocationCloudTagSelector'] = cost_item.provider_cost_allocation_cloud_tag_selector

        # Add the provider metrics
        nb_provider_meters = len(cost_item.provider_meters)
        if nb_provider_meters:
            for i in range(1, nb_provider_meters + 1):
                meter = cost_item.provider_meters[i-1]
                if meter:
                    data['ProviderMeterName%s' % i] = meter['Name']
                    data['ProviderMeterUnit%s' % i] = meter['Unit']
                    data['ProviderMeterValue%s' % i] = meter['Value']

        # Add product information
        data['Product'] = cost_item.product
        if cost_item.product:
            data['ProductAmortizedCost'] = cost_item.product_amortized_cost
            data['ProductOnDemandCost'] = cost_item.product_on_demand_cost
        nb_product_dimensions = len(cost_item.product_dimensions)
        if nb_product_dimensions:
            for i in range(1, nb_product_dimensions + 1):
                dimension = cost_item.product_dimensions[i-1]
                if dimension:
                    data['ProductDimensionName%s' % i] = dimension['Name']
                    data['ProductDimensionElement%s' % i] = dimension['Element']
        nb_product_meters = len(cost_item.product_meters)
        if nb_product_meters:
            for i in range(1, nb_product_meters + 1):
                meter = cost_item.product_meters[i-1]
                if meter:
                    if i == 1:
                        data['ProductMeterName'] = meter['Name']
                        data['ProductMeterUnit'] = meter['Unit']
                        data['ProductMeterValue'] = meter['Value']
                    else:
                        data['ProductMeterName%s' % i] = meter['Name']
                        data['ProductMeterUnit%s' % i] = meter['Unit']
                        data['ProductMeterValue%s' % i] = meter['Value']

        return data

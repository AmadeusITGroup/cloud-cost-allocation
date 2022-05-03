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
            'ProductOnDemandCost',
            'ProductMeterName',
            'ProductMeterUnit',
            'ProductMeterValue'
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
        #for i in range(1, len(cost_item.provider_meter_names) + 1):
        for i in range(1, len(cost_item.provider_meters) + 1):
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
        data['ProductMeterName'] = cost_item.product_meter_name
        data['ProductMeterUnit'] = cost_item.product_meter_unit
        data['ProductMeterValue'] = cost_item.product_meter_value

        return data

# coding: utf-8

# Standard imports
from configparser import ConfigParser
from filecmp import cmp
import logging
import os
import sys
import unittest

# Cloud cost allocation import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from cloud_cost_allocation.config import Config
from cloud_cost_allocation.cloud_cost_allocator import CloudCostAllocator
from cloud_cost_allocation.reader.azure_ea_amortized_cost_reader import AzureEaAmortizedCostReader
from cloud_cost_allocation.reader.csv_cost_allocation_keys_reader import CSV_CostAllocationKeysReader
from cloud_cost_allocation.utils.utils import read_csv_file, write_csv_file
from cloud_cost_allocation.writer.csv_allocated_cost_writer import CSV_AllocatedCostWriter
from cloud_cost_allocation.cost_items import CloudCostItem, ServiceInstance, CostItemFactory


class TestCloudCostItem(CloudCostItem):
    """
    Tests the enhancements of cloud cost items
    """

    __slots__ = (
        'cloud',  # type: str
    )

    def __init__(self):
        super().__init__()
        self.cloud = ""


class TestAzureEaAmortizedCostReader(AzureEaAmortizedCostReader):

    def __init__(self, cost_item_factory: CostItemFactory):
        super().__init__(cost_item_factory)

    def read_item(self, line) -> TestCloudCostItem:
        cost_item = super().read_item(line)
        # Set Azure as cloud provider
        cost_item.cloud = 'az'
        # Set cloud resource id
        cloud_resource_id = line['ResourceId']
        if cloud_resource_id:
            cost_item.tags['cloud_resource_id'] = cloud_resource_id.lower()

        return cost_item


class TestCsvAllocatedCostWriter(CSV_AllocatedCostWriter):

    def __init__(self, service_instances: list[ServiceInstance], config: ConfigParser):
        super().__init__(service_instances, config)

    def get_headers(self) -> list[str]:
        # Add custom columns
        # - Cloud: the cloud provider name, filled for a cloud cost item
        # - IsFinalConsumption: value is Y if the cost item is a leave in the cost allocation graph, N otherwise
        headers = super().get_headers()
        headers.extend(['Cloud', 'IsFinalConsumption'])
        return headers

    def export_item_base(self, cost_item, service_instance) -> dict[str]:
        data = super().export_item_base(cost_item, service_instance)

        has_consumer = service_instance.is_provider()
        data['IsFinalConsumption'] = "Y" if not has_consumer or cost_item.is_self_consumption() else "N"

        return data

    def export_item_cloud(self, cost_item, service_instance) -> dict[str]:
        data = super().export_item_cloud(cost_item, service_instance)
        data['Cloud'] = cost_item.cloud

        return data


class TestCostItemFactory(CostItemFactory):

    def __init__(self, config: Config):
        super().__init__(config)

    def create_cloud_cost_item(self) -> CloudCostItem:
        test_cloud_cost_item = TestCloudCostItem()
        test_cloud_cost_item.initialize(self.config)
        return test_cloud_cost_item


class Test(unittest.TestCase):
    """
    Runs test cases
    """

    # Test cases
    def test_test1(self):
        self.run_test('test1')

    def test_test2(self):
        self.run_test('test2')

    def test_test3(self):
        self.run_test('test3')

    def test_test4(self):
        self.run_test('test4')

    def test_test5(self):
        self.run_test('test5')

    def test_test6(self):
        self.run_test('test6')

    # Auxiliary method
    def run_test(self, test):

        # Set logging INFO level
        logging.getLogger().setLevel(logging.ERROR)

        # Get script directory
        directory = os.path.dirname(os.path.realpath(__file__))

        # Open files
        config_filename = directory + "/" + test + "/" + test + ".cfg"

        # Read config
        file_config = ConfigParser()
        file_config.read(config_filename)
        config = Config(file_config)

        # Create cost item factory
        cost_item_factory = TestCostItemFactory(config)

        # Read costs
        # TODO: when different readers are supported, select the reader and the cloud from the config
        cloud_cost_items = []
        cloud_cost_reader = TestAzureEaAmortizedCostReader(cost_item_factory)
        costs_filename = directory + "/" + test + "/" + test + "_cloud_cost.csv"
        read_csv_file(costs_filename, cloud_cost_reader, cloud_cost_items)

        # Read keys
        consumer_cost_items = []
        cost_allocation_keys_reader = CSV_CostAllocationKeysReader(cost_item_factory)
        allocation_keys_filename = directory + "/" + test + "/" + test + "_cost_allocation_keys.csv"
        read_csv_file(allocation_keys_filename, cost_allocation_keys_reader, consumer_cost_items)

        # Allocate costs
        cloud_cost_allocator = CloudCostAllocator(cost_item_factory)
        cloud_cost_allocator.date_str = consumer_cost_items[0].date_str
        cloud_cost_allocator.currency = "EUR"
        assert_message = test + ": cost allocation failed"
        self.assertTrue(cloud_cost_allocator.allocate(consumer_cost_items, cloud_cost_items), assert_message)

        # Write allocated costs
        allocated_cost_writer = TestCsvAllocatedCostWriter(cloud_cost_allocator.service_instances, config)
        allocated_costs_filename = directory + "/" + test + "/" + test + "_out.csv"
        write_csv_file(allocated_costs_filename, allocated_cost_writer)

        # Compare allocated results with reference
        reference_filename = directory + "/" + test + "/" + test + "_allocated_cost.csv"
        assert_message = test + ": reference cmp failed"
        self.assertTrue(cmp(allocated_costs_filename, reference_filename, shallow=False), assert_message)


if __name__ == '__main__':
    unittest.main()

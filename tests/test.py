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
from cloud_cost_allocation.cloud_cost_allocator import CloudCostItem, CostItemFactory, CloudCostAllocator
from cloud_cost_allocation.azure_ea_amortized_cost_reader import AzureEaAmortizedCostReader
from cloud_cost_allocation.utils import read_csv_file, write_csv_file


class TestCloudCostItem(CloudCostItem):
    """
    Tests the enhancements of cloud cost items
    """

    __slots__ = (
        'cloud',  # type: str
    )

    def __init__(self):
        CloudCostItem.__init__(self)
        self.cloud = ""

    def enhance(self):
        # Set Azure as cloud provider
        self.cloud = 'az'
        # Set cloud resource id
        cloud_resource_id = self.cloud_cost_line['ResourceId']
        if cloud_resource_id:
            self.tags['cloud_resource_id'] = cloud_resource_id.lower()

    def export(self) -> dict[str]:
        row = CloudCostItem.export(self)
        row['Cloud'] = self.cloud
        return row


class TestCostItemFactory(CostItemFactory):

    def create_cloud_cost_item(self) -> CloudCostItem:
        return TestCloudCostItem()


class TestCloudCostAllocator(CloudCostAllocator):
    """
    Tests the addition of a new field in allocated costs
    """

    def __init__(self, cost_item_factory: CostItemFactory, config: ConfigParser):
        CloudCostAllocator.__init__(self, cost_item_factory, config)

    def get_headers(self) -> list[str]:
        # Add custom columns
        # - Cloud: the cloud provider name, filled for a cloud cost item
        # - IsFinalConsumption: value is Y if the cost item is a leave in the cost allocation graph, N otherwise
        headers = super().get_headers()
        headers.extend(['Cloud', 'IsFinalConsumption'])
        return headers

    def write(self, writer) -> None:
        # Process cost items
        for service_instance_id in sorted(self.service_instances.keys()):
            service_instance = self.service_instances[service_instance_id]
            has_consumer = True if service_instance.consumer_cost_items else False
            for cost_item in service_instance.cost_items:

                # Write fields
                row = cost_item.export()
                row['IsFinalConsumption'] = "Y" if not has_consumer or cost_item.is_self_consumption() else "N"
                writer.writerow(row)


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

    # Auxiliary method
    def run_test(self, test):

        # Set logging INFO level
        logging.getLogger().setLevel(logging.ERROR)

        # Get script directory
        directory = os.path.dirname(os.path.realpath(__file__))

        # Open files
        config_filename = directory + "/" + test + "/" + test + ".cfg"

        # Read config
        config = ConfigParser()
        config.read(config_filename)

        # Create cost item factory
        cost_item_factory = TestCostItemFactory()

        # Read costs
        # TODO: when different readers are supported, select the reader and the cloud from the config
        cloud_cost_items = []
        cloud_cost_reader = AzureEaAmortizedCostReader(cost_item_factory, config)
        costs_filename = directory + "/" + test + "/" + test + "_cloud_cost.csv"
        read_csv_file(costs_filename, cloud_cost_reader, cloud_cost_items)
        for cloud_cost_item in cloud_cost_items:
            cloud_cost_item.enhance()

        # Read keys
        consumer_cost_items = []
        cloud_cost_allocator = TestCloudCostAllocator(cost_item_factory, config)
        allocation_keys_filename = directory + "/" + test + "/" + test + "_cost_allocation_keys.csv"
        read_csv_file(allocation_keys_filename, cloud_cost_allocator, consumer_cost_items)

        # Allocate costs
        assert_message = test + ": cost allocation failed"
        self.assertTrue(cloud_cost_allocator.allocate(consumer_cost_items, cloud_cost_items), assert_message)

        # Write allocated costs
        allocated_costs_filename = directory + "/" + test + "/" + test + "_out.csv"
        write_csv_file(allocated_costs_filename, cloud_cost_allocator)

        # Compare allocated results with reference
        reference_filename = directory + "/" + test + "/" + test + "_allocated_cost.csv"
        assert_message = test + ": reference cmp failed"
        self.assertTrue(cmp(allocated_costs_filename, reference_filename, shallow=False), assert_message)


if __name__ == '__main__':
    unittest.main()
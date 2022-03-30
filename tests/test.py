# coding: utf-8

# Standard imports
from configparser import ConfigParser
from csv import DictWriter
from filecmp import cmp
import logging
import os
import sys
import unittest
from typing import TextIO

# Cloud cost allocation import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import cloud_cost_allocation.cloud_cost_allocator
import cloud_cost_allocation.azure_ea_amortized_cost_reader


class TestCloudCostItem(cloud_cost_allocation.cloud_cost_allocator.CloudCostItem):
    """
    Tests the enhancements of cloud cost items
    """

    __slots__ = (
        'cloud',  # type: str
    )

    def __init__(self):
        cloud_cost_allocation.cloud_cost_allocator.CloudCostItem.__init__(self)
        self.cloud = ""

    def enhance(self):
        # Set Azure as cloud provider
        self.cloud = 'az'
        # Set cloud resource id
        cloud_resource_id = self.cloud_cost_line['ResourceId']
        if cloud_resource_id:
            self.tags['cloud_resource_id'] = cloud_resource_id.lower()

    def write_to_csv_row(self, csv_row: dict[str]) -> None:
        cloud_cost_allocation.cloud_cost_allocator.CloudCostItem.write_to_csv_row(self, csv_row)
        csv_row['Cloud'] = self.cloud


class TestCostItemFactory(cloud_cost_allocation.cloud_cost_allocator.CostItemFactory):

    def create_cloud_cost_item(self) -> cloud_cost_allocation.cloud_cost_allocator.CloudCostItem:
        return TestCloudCostItem()


class TestCloudCostAllocator(cloud_cost_allocation.cloud_cost_allocator.CloudCostAllocator):
    """
    Tests the addition of a new field in allocated costs
    """

    def __init__(self,
                 cost_item_factory: cloud_cost_allocation.cloud_cost_allocator.CostItemFactory,
                 config: ConfigParser):
        cloud_cost_allocation.cloud_cost_allocator.CloudCostAllocator.__init__(self, cost_item_factory, config)

    def write_allocated_cost(self, allocated_cost_stream: TextIO) -> None:

        # Add custom columns
        # - Cloud: the cloud provider name, filled for a cloud cost item
        # - IsFinalConsumption: value is Y if the cost item is a leave in the cost allocation graph, N otherwise
        csv_header = self.get_cost_item_csv_header()
        csv_header.extend(['Cloud', 'IsFinalConsumption'])

        # pen CSV file and write header
        writer = DictWriter(allocated_cost_stream, fieldnames=csv_header, restval='', extrasaction='ignore')
        writer.writeheader()

        # Process cost items
        for service_instance_id in sorted(self.service_instances.keys()):
            service_instance = self.service_instances[service_instance_id]
            has_consumer = True if service_instance.consumer_cost_items else False
            for cost_item in service_instance.cost_items:

                # Write fields
                row = {}
                cost_item.write_to_csv_row(row)
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
        cloud_cost_reader =\
            cloud_cost_allocation.azure_ea_amortized_cost_reader.AzureEaAmortizedCostReader(cost_item_factory, config)
        cloud_cost_reader.read(cloud_cost_items, directory + "/" + test + "/" + test + "_cloud_cost.csv")
        for cloud_cost_item in cloud_cost_items:
            cloud_cost_item.cloud = 'az'
            cloud_cost_item.add_cloud_resource_id_tag(cloud_cost_item.cloud_cost_line['ResourceId'])
            cloud_cost_item.enhance()

        # Read keys
        consumer_cost_items = []
        cloud_cost_allocator = TestCloudCostAllocator(cost_item_factory, config)
        cloud_cost_allocator.read_cost_allocation_key(consumer_cost_items, directory + "/" + test + "/" + test + "_cost_allocation_keys.csv")

        # Allocate costs
        assert_message = test + ": cost allocation failed"
        self.assertTrue(cloud_cost_allocator.allocate(consumer_cost_items, cloud_cost_items), assert_message)

        # Write allocated costs
        allocated_costs_filename = directory + "/" + test + "/" + test + "_out.csv"
        with open(allocated_costs_filename, 'w', newline='') as allocated_costs:
            cloud_cost_allocator.write_allocated_cost(allocated_costs)

        # Compare allocated results with reference
        reference_filename = directory + "/" + test + "/" + test + "_allocated_cost.csv"
        assert_message = test + ": reference cmp failed"
        self.assertTrue(cmp(allocated_costs_filename, reference_filename, shallow=False), assert_message)


if __name__ == '__main__':
    unittest.main()
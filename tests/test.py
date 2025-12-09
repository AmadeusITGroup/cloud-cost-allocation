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
from cloud_cost_allocation.reader.csv_allocated_cost_reader import CSV_AllocatedCostReader
from cloud_cost_allocation.reader.azure_ea_amortized_cost_reader import AzureEaAmortizedCostReader
from cloud_cost_allocation.reader.csv_cost_allocation_keys_reader import CSV_CostAllocationKeysReader
from cloud_cost_allocation.reader.csv_focus_reader import CSV_FocusReader
from cloud_cost_allocation.utils.utils import read_csv_file, write_csv_file
from cloud_cost_allocation.writer.csv_allocated_cost_writer import CSV_AllocatedCostWriter
from cloud_cost_allocation.cost_items import CloudCostItem, ConsumerCostItem, CostItem, ServiceInstance, CostItemFactory


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

    def get_cost_allocation_key(self, index):
        return 0

    def get_provider_service(self):
        return ""

    def set_cost_allocation_key(self, index, value):
        pass

    def set_amount(self, amount_index: int, amount: float):
        self.amounts[amount_index] = amount


class TestConsumerCostItem(ConsumerCostItem):
    """
    Tests the enhancements of consumer cost items
    """

    __slots__ = (
        'product_info',  # type: str
    )

    def __init__(self):
        super().__init__()
        self.product_info = ""

    def get_cost_allocation_key(self, index):
        return self.allocation_keys[index]

    def get_provider_service(self):
        return self.provider_service

    def set_cost_allocation_key(self, index, value):
        self.allocation_keys[index] = value

    def set_amount(self, amount_index: int, amount: float):
        self.amounts[amount_index] = amount
        self.unallocated_product_amounts[amount_index] = amount


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


class TestCostAllocationKeysReader(CSV_CostAllocationKeysReader):

    def __init__(self, cost_item_factory: CostItemFactory):
        super().__init__(cost_item_factory)

    def read_item(self, line) -> TestCloudCostItem:
        cost_item = super().read_item(line)
        # Set product info
        if 'ProductInfo' in line:
            cost_item.product_info = line['ProductInfo'].lower()
        return cost_item


class TestCsvAllocatedCostReader(CSV_AllocatedCostReader):

    def __init__(self, cost_item_factory: CostItemFactory):
        super().__init__(cost_item_factory)

    def read_cloud_cost_item(self, line) -> TestCloudCostItem:
        cost_item = super().read_cloud_cost_item(line)
        # Set cloud provider
        cost_item.cloud = line['Cloud']
        return cost_item

    def read_consumer_cost_item(self, line) -> TestConsumerCostItem:
        cost_item = super().read_consumer_cost_item(line)
        # Set product info
        cost_item.product_info = line['ProductInfo']
        return cost_item


class TestCsvAllocatedCostWriter(CSV_AllocatedCostWriter):

    def __init__(self, service_instances: list[ServiceInstance], config: ConfigParser):
        super().__init__(service_instances, config)

    def get_headers(self) -> list[str]:
        # Add custom columns
        # - Cloud: the cloud provider name, filled for a cloud cost item
        # - IsFinalConsumption: value is Y if the cost item is a leave in the cost allocation graph, N otherwise
        headers = super().get_headers()
        headers.extend(['Cloud', 'IsFinalConsumption', 'ProductInfo'])
        return headers

    def export_item_base(self, cost_item, service_instance) -> dict[str]:
        for i in range(len(cost_item.amounts)):
            cost_item.amounts[i] = round(cost_item.amounts[i], 4)
        data = super().export_item_base(cost_item, service_instance)
        has_consumer = service_instance.is_provider()
        data['IsFinalConsumption'] = "Y" if not has_consumer or cost_item.is_self_consumption() else "N"
        return data

    def export_item_cloud(self, cost_item, service_instance) -> dict[str]:
        data = super().export_item_cloud(cost_item, service_instance)
        data['Cloud'] = cost_item.cloud
        return data

    def export_item_consumer(self, cost_item, service_instance) -> dict[str]:
        for i in range(len(cost_item.unallocated_product_amounts)):
            cost_item.unallocated_product_amounts[i] = round(cost_item.unallocated_product_amounts[i], 4)
        for i in range(len(cost_item.product_amounts)):
            cost_item.product_amounts[i] = round(cost_item.product_amounts[i], 4)
        data = super().export_item_consumer(cost_item, service_instance)
        if cost_item.product_info:
            data['ProductInfo'] = cost_item.product_info
        return data


class TestCostItemFactory(CostItemFactory):

    def __init__(self, config: Config):
        super().__init__(config)

    def create_cloud_cost_item(self) -> CloudCostItem:
        test_cloud_cost_item = TestCloudCostItem()
        test_cloud_cost_item.initialize(self.config)
        return test_cloud_cost_item

    def create_consumer_cost_item(self) -> ConsumerCostItem:
        test_consumer_cost_item = TestConsumerCostItem()
        test_consumer_cost_item.initialize(self.config)
        return test_consumer_cost_item


class TestCloudCostAllocator(CloudCostAllocator):
    def __init__(self, config: Config):
        super().__init__(config)

    def update_default_product_from_consumer_cost_item(self,
                                                       new_consumer_cost_item: ConsumerCostItem,
                                                       default_product_consumer_cost_item: ConsumerCostItem):
        super().update_default_product_from_consumer_cost_item(new_consumer_cost_item,
                                                               default_product_consumer_cost_item)
        new_consumer_cost_item.product_info = default_product_consumer_cost_item.product_info

    def update_default_product_from_config(self, new_consumer_cost_item: ConsumerCostItem):
        super().update_default_product_from_config(new_consumer_cost_item)
        new_consumer_cost_item.product_info = "0"


class Test(unittest.TestCase):
    """
    Runs test cases
    """

    # Test cases
    def test_test1(self):
        self.run_allocation('test1')

    def test_test2(self):
        self.run_allocation('test2')

    def test_test3(self):
        self.run_allocation('test3')

    def test_test4(self):
        self.run_allocation('test4')

    def test_test5(self):
        self.run_allocation('test5')

    def test_test6(self):
        self.run_allocation('test6')

    def test_test7(self):
        self.run_further_allocation('test7', self.load_further_amount_test7)

    def test_test8(self):
        self.run_allocation('test8')

    def test_test9(self):
        self.run_allocation('test9')

    def test_test10(self):
        self.run_allocation('test10')

    def test_test11(self):
        self.run_allocation('test11')

    def test_test12(self):
        self.run_allocation('test12')

    # Auxiliary methods
    def load_further_amount_test7(self, cost_items: list[CostItem]):
        for cost_item in cost_items:

            # Populate CO2 amount (index 2) and CO2 allocation key (index 1)
            if cost_item.service == 'container':  # CO2 set at IaaS level
                cost_item.set_amount(2, 10)
            elif cost_item.get_provider_service() == 'container':  # Different CO2 allocation than cost
                if cost_item.service == 'application1':
                    cost_item.set_cost_allocation_key(1, 60)
                elif cost_item.service == 'application2':
                    cost_item.set_cost_allocation_key(1, 40)
            else: # Same CO2 allocation as cost
                cost_item.set_cost_allocation_key(1, cost_item.get_cost_allocation_key(0))

            # Populate electricity power (index 3)
            if cost_item.get_provider_service() == 'container':  # Electricity power set application container level
                if cost_item.service == 'application1':
                    cost_item.set_amount(3, 0.6)
                elif cost_item.service == 'application2':
                    cost_item.set_amount(3, 0.4)

    def run_allocation(self, test: str):

        # Set logging level
        logging.getLogger().setLevel(logging.FATAL)

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

        # Get the cloud cost reader
        cloud_cost_reader = None
        if 'Test' in file_config and 'CloudCostReader' in file_config['Test']:
            cloud_cost_reader_str = file_config['Test']['CloudCostReader']
            if cloud_cost_reader_str == "Focus":
                cloud_cost_reader = CSV_FocusReader(cost_item_factory)
            elif cloud_cost_reader_str == "AzureEaAmortizedCost":
                cloud_cost_reader = TestAzureEaAmortizedCostReader(cost_item_factory)
        if cloud_cost_reader is None:
            logging.fatal(" None or invalid cloud cost reader defined in config file for " + test)
            sys.exit(1)

        # Read costs
        cloud_cost_items = []
        costs_filename = directory + "/" + test + "/" + test + "_cloud_cost.csv"
        read_csv_file(costs_filename, cloud_cost_reader, cloud_cost_items)

        # Read keys
        consumer_cost_items = []
        cost_allocation_keys_reader = TestCostAllocationKeysReader(cost_item_factory)
        allocation_keys_filename = directory + "/" + test + "/" + test + "_cost_allocation_keys.csv"
        read_csv_file(allocation_keys_filename, cost_allocation_keys_reader, consumer_cost_items)

        # Allocate costs
        cloud_cost_allocator = TestCloudCostAllocator(cost_item_factory)
        cloud_cost_allocator.date_str = consumer_cost_items[0].date_str
        cloud_cost_allocator.currency = "EUR"
        assert_message = test + ": cost allocation failed"
        self.assertTrue(cloud_cost_allocator.allocate(consumer_cost_items, cloud_cost_items, config.amounts),
                        assert_message)

        # Write allocated costs
        allocated_cost_writer = TestCsvAllocatedCostWriter(cloud_cost_allocator.service_instances, config)
        allocated_costs_filename = directory + "/" + test + "/" + test + "_out.csv"
        write_csv_file(allocated_costs_filename, allocated_cost_writer)

        # Compare allocated results with reference
        reference_filename = directory + "/" + test + "/" + test + "_allocated_cost.csv"
        assert_message = test + ": reference cmp failed"
        self.assertTrue(cmp(allocated_costs_filename, reference_filename, shallow=False), assert_message)

    def run_further_allocation(self, test: str, load_further_amount_method: classmethod):

        # Set logging level
        logging.getLogger().setLevel(logging.INFO)

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

        # Read allocated costs
        allocated_cost_items = []
        csv_allocated_cost_reader = TestCsvAllocatedCostReader(cost_item_factory)
        allocated_cost_filename = directory + "/" + test + "/" + test + "_allocated_cost.csv"
        read_csv_file(allocated_cost_filename, csv_allocated_cost_reader, allocated_cost_items)

        # Load further amounts
        load_further_amount_method(allocated_cost_items)

        # Allocate further amounts
        cloud_cost_allocator = CloudCostAllocator(cost_item_factory)
        assert_message = test + ": cost allocation failed"
        self.assertTrue(cloud_cost_allocator.allocate_further_amounts(allocated_cost_items,
                                                                      config.amounts[2:]),
                        assert_message)

        # Write further allocated costs
        further_allocated_cost_writer = TestCsvAllocatedCostWriter(cloud_cost_allocator.service_instances, config)
        further_allocated_costs_filename = directory + "/" + test + "/" + test + "_out.csv"
        write_csv_file(further_allocated_costs_filename, further_allocated_cost_writer)

        # Compare allocated results with reference
        reference_filename = directory + "/" + test + "/" + test + "_further_allocated_cost.csv"
        assert_message = test + ": reference cmp failed"
        self.assertTrue(cmp(further_allocated_costs_filename, reference_filename, shallow=False), assert_message)


if __name__ == '__main__':
    unittest.main()

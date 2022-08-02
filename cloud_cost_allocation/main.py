# coding: utf-8

# Standard imports
from configparser import ConfigParser
from logging import basicConfig, error, info, INFO
from optparse import OptionParser
from sys import exit

# Cloud cost allocation import
from cloud_cost_allocation.cloud_cost_allocator import CloudCostAllocator
from cloud_cost_allocation.cost_items import CostItemFactory
from cloud_cost_allocation.reader.azure_ea_amortized_cost_reader import AzureEaAmortizedCostReader
from cloud_cost_allocation.reader.csv_cost_allocation_keys_reader import CSV_CostAllocationKeysReader
from cloud_cost_allocation.utils.utils import read_csv, write_csv_file
from cloud_cost_allocation.writer.csv_allocated_cost_writer import CSV_AllocatedCostWriter


def main():
    """
    Command line
    """

    # Configure logging
    basicConfig(format='%(asctime)s %(levelname)-8s %(message)s',
                level=INFO,
                datefmt='%Y-%m-%d %H:%M:%S')

    # Parse arguments
    parser = OptionParser()
    parser.add_option("-C", "--config", help="Configuration file", action="store")
    parser.add_option("-c", "--cost", help="Cloud cost CSV files, prefixed with their types and colon character, for example: AzEaAmo:az_costs.csv", action="append")
    parser.add_option("-k", "--keys", help="Cost allocation key CSV files", action="append", default=[])
    parser.add_option("-o", "--output", help="The output allocated cost CSV file", action="store", default="")
    (options, _) = parser.parse_args()

    # Check options
    if not options.config:
        error("--config is mandatory")
        exit(255)
    if not options.cost:
        error("--cost is mandatory")
        exit(255)
    if not options.output:
        error("--output is mandatory")
        exit(255)

    # Read config
    config = ConfigParser()
    config.read(options.config)

    # Create cost item factory
    cost_item_factory = CostItemFactory()

    # Read costs
    cloud_cost_items = []
    for cost in options.cost:
        cost_list = cost.split(':')
        cost_type = cost_list[0]
        cost_file = cost_list[1]
        if cost_type == 'AzEaAmo':
            cloud_cost_reader = AzureEaAmortizedCostReader(cost_item_factory, config)
            info("Reading Azure Enterprise Agreement amortized costs: " + cost_file)
            read_csv(cost_file, cloud_cost_reader, cloud_cost_items)
        else:
            error("Unknown cost type: " + cost_type)
            exit(2)

    # Read keys
    consumer_cost_items = []
    cost_allocation_reader = CSV_CostAllocationKeysReader(cost_item_factory, config)
    for key in options.keys:
        info("Reading cost allocation keys: " + key)
        read_csv(key, cost_allocation_reader, consumer_cost_items)

    # Allocate costs
    cloud_cost_allocator = CloudCostAllocator(cost_item_factory, config)
    if not cloud_cost_allocator.allocate(consumer_cost_items, cloud_cost_items):
        error("Cost allocation failed")
        exit(3)

    # Write allocated costs
    allocated_cost_writer = CSV_AllocatedCostWriter(cloud_cost_allocator.service_instances, config)
    write_csv_file(options.output, allocated_cost_writer)


if __name__ == '__main__':
    main()

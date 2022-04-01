from configparser import ConfigParser
from logging import error, getLogger, INFO
from optparse import OptionParser
from sys import exit

from cloud_cost_allocation.cloud_cost_allocator import CloudCostAllocator, CostItemFactory
from cloud_cost_allocation.azure_ea_amortized_cost_reader import AzureEaAmortizedCostReader
from cloud_cost_allocation.utils import read_csv, write_csv_file


def main():
    """
    Command line
    """
    # Set logging INFO level
    getLogger().setLevel(INFO)

    # Parse arguments
    parser = OptionParser()
    parser.add_option("-C", "--config", help="Configuration file", action="store")
    parser.add_option("-c", "--cost", help="Cloud cost CSV files, prefixed with their types and colon character, for example: AzureEaAmortizedCost:az_costs.csv", action="append")
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
        if cost_type == 'AzEaAmo':
            cloud_cost_reader = AzureEaAmortizedCostReader(cost_item_factory, config)
            read_csv(cost_list[1], cloud_cost_reader, cloud_cost_items)
        else:
            error("Unknown cost type: " + cost_type)
            exit(2)

    # Read keys
    consumer_cost_items = []
    cloud_cost_allocator = CloudCostAllocator(cost_item_factory, config)
    for key in options.keys:
        read_csv(key, cloud_cost_allocator, consumer_cost_items)

    # Allocate costs
    if not cloud_cost_allocator.allocate(consumer_cost_items, cloud_cost_items):
        error("Cost allocation failed")
        exit(3)

    # Write allocated costs
    write_csv_file(options.output, cloud_cost_allocator)


if __name__ == '__main__':
    main()

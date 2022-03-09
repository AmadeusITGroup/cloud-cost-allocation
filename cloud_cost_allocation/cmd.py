from cloud_cost_allocator import CloudCostAllocator, CostItemFactory
from azure_ea_amortized_cost_reader import AzureEaAmortizedCostReader
from configparser import ConfigParser
from logging import error
from optparse import OptionParser
from sys import exit
from typing import TextIO

def cmd():
    """
    Command line
    """
    # Set logging INFO level
    logging.getLogger().setLevel(logging.INFO)

    # Parse arguments
    parser = OptionParser()
    parser.add_option("-C", "--config", help="Configuration file", action="store")
    parser.add_option("-c", "--cost", help="Cloud cost CSV files, prefixed with their types and colon character, for example: AzureEaAmortizedCost:az_costs.csv", action="append")
    parser.add_option("-k", "--keys", help="Cost allocation key CSV files", action="append", default=[])
    parser.add_option("-o", "--output", help="The output allocated cost CSV file", action="store", default="")
    (options, args) = parser.parse_args()

    # Check options
    if not options.config:
        error("--config is mandatory")
        sys.exit(1)
    if not options.cost:
        error("--cost is mandatory")
        sys.exit(1)
    if not options.output:
        error("--output is mandatory")
        sys.exit(1)

    # Read config
    config = ConfigParser()
    config.read(options.config)

    # Create cost item factory
    cost_item_factory = CostItemFactory()

    # Read costs
    cost_items = []
    for cost in options.cost:
        cost_list = cost.split(':')
        cost_type = cost_list[0]
        cost_text_io = open(cost_list[1], 'r')
        if cost_type == 'AzureEaAmortizedCost':
            cloud_cost_reader = AzureEaAmortizedCostReader(config)
            cloud_cost_reader.read(cost_items, cost_item_factory, cost_text_io)
        else:
            error("Unknown cost type: " + cost_type)
            sys.exit(1)
        cost_text_io.close()

    # Read keys
    cloud_cost_allocator = CloudCostAllocator(config)
    for key in options.keys:
        cost_allocation_key_text_io = open(key, 'r')
        cloud_cost_allocator.read_cost_allocation_key(cost_items, cost_item_factory, cost_allocation_key_text_io):
        cost_allocation_key_text_io.close()

    # Allocate costs
    if not cloud_cost_allocator.allocate(cost_items):
        error("Cost allocation failed")
        exit(1)

    # Write allocated costs
    allocated_cost_text_io = open(options.output, 'w', newline='')
    cloud_cost_allocator.write_allocated_cost(allocated_cost_text_io)
    allocated_cost_text_io.close()

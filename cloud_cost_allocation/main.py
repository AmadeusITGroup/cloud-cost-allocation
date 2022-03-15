import cloud_cost_allocation.cloud_cost_allocator
import cloud_cost_allocation.azure_ea_amortized_cost_reader
from configparser import ConfigParser
import logging
from optparse import OptionParser
import sys


def main():
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
        logging.error("--config is mandatory")
        sys.exit(1)
    if not options.cost:
        logging.error("--cost is mandatory")
        sys.exit(1)
    if not options.output:
        logging.error("--output is mandatory")
        sys.exit(1)

    # Read config
    config = ConfigParser()
    config.read(options.config)

    # Create cost item factory
    cost_item_factory = cloud_cost_allocation.cloud_cost_allocator.CostItemFactory()

    # Read costs
    cloud_cost_items = []
    for cost in options.cost:
        cost_list = cost.split(':')
        cost_type = cost_list[0]
        cost_text_io = open(cost_list[1], 'r')
        if cost_type == 'AzEaAmo':
            cloud_cost_reader = cloud_cost_allocation.azure_ea_amortized_cost_reader.AzureEaAmortizedCostReader\
                (cost_item_factory, config)
            cloud_cost_reader.read(cloud_cost_items, cost_text_io)
        else:
            logging.error("Unknown cost type: " + cost_type)
            sys.exit(1)
        cost_text_io.close()

    # Read keys
    consumer_cost_items = []
    cloud_cost_allocator = cloud_cost_allocation.cloud_cost_allocator.CloudCostAllocator(cost_item_factory, config)
    for key in options.keys:
        cost_allocation_key_text_io = open(key, 'r')
        cloud_cost_allocator.read_cost_allocation_key(consumer_cost_items, cost_allocation_key_text_io)
        cost_allocation_key_text_io.close()

    # Allocate costs
    if not cloud_cost_allocator.allocate(consumer_cost_items, cloud_cost_items):
        logging.error("Cost allocation failed")
        exit(1)

    # Write allocated costs
    allocated_cost_text_io = open(options.output, 'w', newline='')
    cloud_cost_allocator.write_allocated_cost(allocated_cost_text_io)
    allocated_cost_text_io.close()


if __name__ == '__main__':
    main()

from cloud_cost_allocation.cloud_cost_allocator import CloudCostAllocator, CostItemFactory
from cloud_cost_allocation.azure_ea_amortized_cost_reader import AzureEaAmortizedCostReader
from configparser import ConfigParser
from logging import error, getLogger, INFO
from optparse import OptionParser
from sys import exit


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
            cloud_cost_reader.read(cloud_cost_items, cost_list[1])
        else:
            error("Unknown cost type: " + cost_type)
            exit(2)

    # Read keys
    consumer_cost_items = []
    cloud_cost_allocator = CloudCostAllocator(cost_item_factory, config)
    for key in options.keys:
        cloud_cost_allocator.read_cost_allocation_key(consumer_cost_items, key)

    # Allocate costs
    if not cloud_cost_allocator.allocate(consumer_cost_items, cloud_cost_items):
        error("Cost allocation failed")
        exit(3)

    # Write allocated costs
    with open(options.output, 'w', newline='') as allocated_cost_text_io:
        cloud_cost_allocator.write_allocated_cost(allocated_cost_text_io)


if __name__ == '__main__':
    main()

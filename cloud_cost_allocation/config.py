# coding: utf-8

from configparser import ConfigParser
from logging import error
import re


class Config(object):

    """"
    Guess what it is
    """

    __slots__ = (
        'config',                                # type: ConfigParser
        'date_format',                           # type: str
        'default_service',                       # type: str
        'default_product',                       # type: str
        'service_tag_keys',                      # type: list[str]
        'instance_tag_keys',                     # type: list[str]
        'consumer_service_tag_keys',             # type: list[str]
        'consumer_service_ignored_tag_values',   # type: list[str]
        'consumer_instance_tag_keys',            # type: list[str]
        'product_tag_keys',                      # type: list[str]
        'dimensions',                            # type: list[str]
        'dimension_tag_keys',                    # type: dict[list[str]]
        'consumer_dimension_tag_keys',           # type: dict[list[str]]
        'amounts',                               # type: list[str]
        'nb_amounts',                            # type: int
        'allocation_keys',                       # type: list[str]
        'nb_allocation_keys',                    # type: int
        'amount_to_allocation_key_indexes',      # type: dict[int]
                                                 # Key is amount index, value is allocation key index
        'nb_provider_meters',                    # type: int
        'nb_product_dimensions',                 # type: int
        'nb_product_meters',                     # type: int
    )

    def __init__(self, config: ConfigParser):

        # Config
        self.config = config

        # Date format
        if 'General' in config and 'DateFormat' in config['General']:
            self.date_format = config['General']['DateFormat']
        else:
            error("Missing date format, assuming %Y-%m-%d")
            self.date_format = "%Y-%m-%d"

        # Default service
        if 'General' in config and 'DefaultService' in config['General']:
            self.default_service = config['General']['DefaultService'].strip().lower()

        # Default product
        if 'General' in config and 'DefaultProduct' in config['General']:
            self.default_product = config['General']['DefaultProduct'].strip().lower()
        else:
            self.default_product = ''

        # Service tag keys
        self.service_tag_keys = []
        if 'TagKey' in config and 'Service' in config['TagKey']:
            for service_tag_key in self.config['TagKey']['Service'].split(","):
                self.service_tag_keys.append(service_tag_key.strip().lower())

        # Instance tag keys
        self.instance_tag_keys = []
        if 'TagKey' in config and 'Instance' in config['TagKey']:
            for instance_tag_key in self.config['TagKey']['Instance'].split(","):
                self.instance_tag_keys.append(instance_tag_key.strip().lower())

        # Consumer service tag keys
        self.consumer_service_tag_keys = []
        if 'TagKey' in config and 'ConsumerService' in config['TagKey']:
            for consumer_service_tag_key in self.config['TagKey']['ConsumerService'].split(","):
                self.consumer_service_tag_keys.append(consumer_service_tag_key.strip().lower())

        # Consumer service ignored tag values
        self.consumer_service_ignored_tag_values = []
        if 'TagKey' in config and 'ConsumerServiceIgnoredValue' in config['TagKey']:
            for consumer_service_tag_ignored_value in self.config['TagKey']['ConsumerServiceIgnoredValue'].split(","):
                self.consumer_service_ignored_tag_values.append(consumer_service_tag_ignored_value.strip().lower())

        # Consumer instance tag keys
        self.consumer_instance_tag_keys = []
        if 'TagKey' in config and 'ConsumerInstance' in config['TagKey']:
            for consumer_instance_tag_key in self.config['TagKey']['ConsumerInstance'].split(","):
                self.consumer_instance_tag_keys.append(consumer_instance_tag_key.strip().lower())

        # Product tag keys
        self.product_tag_keys = []
        if 'TagKey' in config and 'Product' in config['TagKey']:
            for product_tag_key in self.config['TagKey']['Product'].split(","):
                self.product_tag_keys.append(product_tag_key.strip().lower())

        # Dimensions
        self.dimensions = []
        if 'General' in config and 'Dimensions' in self.config['General']:
            for dimension in self.config['General']['Dimensions'].split(','):
                self.dimensions.append(dimension.strip())

        # Dimension tag keys
        self.dimension_tag_keys = {}
        for dimension in self.dimensions:
            current_dimension_tag_keys = []
            if 'TagKey' in config and dimension in config['TagKey']:
                for dimension_tag_key in self.config['TagKey'][dimension].split(","):
                    current_dimension_tag_keys.append(dimension_tag_key.strip().lower())
            self.dimension_tag_keys[dimension] = current_dimension_tag_keys

        # Consumer dimension tag keys
        self.consumer_dimension_tag_keys = {}
        for dimension in self.dimensions:
            current_consumer_dimension_tag_keys = []
            consumer_dimension = 'Consumer' + dimension
            if 'TagKey' in config and consumer_dimension in config['TagKey']:
                for consumer_dimension_tag_key in self.config['TagKey'][consumer_dimension].split(","):
                    current_consumer_dimension_tag_keys.append(consumer_dimension_tag_key.strip().lower())
            self.consumer_dimension_tag_keys[dimension] = current_consumer_dimension_tag_keys

        # Amounts
        self.amounts = []
        if 'General' in self.config and 'Amounts' in self.config['General']:
            for amount in self.config['General']['Amounts'].split(","):
                self.amounts.append(amount.strip())
        self.nb_amounts = len(self.amounts)

        # Allocation keys
        self.allocation_keys = []
        if 'General' in self.config and 'AllocationKeys' in self.config['General']:
            for allocation_key in self.config['General']['AllocationKeys'].split(","):
                self.allocation_keys.append(allocation_key.strip())
        self.nb_allocation_keys = len(self.allocation_keys)

        # Amount to allocation key indexes
        self.amount_to_allocation_key_indexes = {}
        if 'General' in config and 'AmountAllocationKeys' in config['General']:
            for amount_allocation_key in config['General']['AmountAllocationKeys'].split(","):
                if amount_allocation_key:
                    match = re.match("([^:]+):([^:]*)", amount_allocation_key)
                    if match:
                        amount = match.group(1).strip()
                        if amount in self.amounts:
                            amount_index = self.amounts.index(amount)
                        else:
                            error("Amount '" + amount +
                                  "' present in AmountAllocationKeys is missing in Amounts")
                            continue
                        allocation_key = match.group(2).strip()
                        if allocation_key in self.allocation_keys:
                            allocation_key_index = self.allocation_keys.index(allocation_key)
                        else:
                            error("Allocation key '" + allocation_key +
                                  "' present in AmountAllocationKeys is missing in AllocationKeys")
                            continue
                        self.amount_to_allocation_key_indexes[amount_index] = allocation_key_index
                    else:
                        error("Unexpected AmountAllocationKeys format: '" + amount_allocation_key + "'")
                        continue

        # Defensive check: every amount should have an allocation key
        for amount_index in range(len(self.amounts)):
            if amount_index not in self.amount_to_allocation_key_indexes:
                error("Further amount '" + self.amounts[amount_index] +
                      "' present in Amounts is missing in AmountAllocationKeys")
                continue

        # Number of provider meters
        if 'General' in config and 'NumberOfProviderMeters' in self.config['General']:
            self.nb_provider_meters = int(self.config['General']['NumberOfProviderMeters'])
        else:
            self.nb_provider_meters = 0

        # Number of product dimensions and product meters
        if 'General' in config and 'NumberOfProductDimensions' in self.config['General']:
            self.nb_product_dimensions = int(self.config['General']['NumberOfProductDimensions'])
        else:
            self.nb_product_dimensions = 0
        if 'General' in config and 'NumberOfProductMeters' in self.config['General']:
            self.nb_product_meters = int(self.config['General']['NumberOfProductMeters'])
        else:
            self.nb_product_meters = 0

    def build_amount_to_allocation_key_indexes(self, amount_allocation_key_indexes: dict[int], amounts: list[str]):
        # Return False if any input amount is missing in configuration
        for amount in amounts:
            if amount in self.amounts:
                amount_index = self.amounts.index(amount)
                allocation_key_index = self.amount_to_allocation_key_indexes[amount_index]
                amount_allocation_key_indexes[amount_index] = allocation_key_index
            else:
                error("Amount is missing in configuration: '" + amount + "'")
                return False
        return True

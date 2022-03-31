# coding: utf-8

from configparser import ConfigParser
from io import StringIO
from logging import info, error
import re
import sys


class CostItem(object):
    """
    Represents a cost item, which comes either from the cloud or from a cost allocation key
    """

    __slots__ = (
        # Fields
        'date_str',                             # type: str
        'service',                              # type: str
        'instance',                             # type: str
        'dimensions',                           # type: dict[str,str]
        'tags',                                 # type: dict[str,str]
        'amortized_cost',                       # type: float
        'on_demand_cost',                       # type: float
        'currency',                             # type: str

        # Helpers
        'cost',                                 # type: float
        'nb_matching_provider_tag_selectors',   # type: int
    )

    def __init__(self):
        self.date_str = ""
        self.service = ""
        self.instance = ""
        self.dimensions = {}
        self.tags = {}
        self.cost = 0.0
        self.amortized_cost = 0.0
        self.on_demand_cost = 0.0
        self.currency = ""
        self.nb_matching_provider_tag_selectors = 0

    def get_product(self) -> str:
        # Default behavior, overridden in child classes
        return ''

    def get_product_meter_name(self) -> str:
        # Default behavior, overridden in child classes
        return ''

    def is_self_consumption(self) -> bool:
        # Default behavior, overridden in child classes
        return False

    def matches_cloud_tag_selector(self, cloud_tag_selector: str, provider_service: str) -> bool:
        return False

    def reset_cost(self) -> None:
        self.cost = 0.0

    def reset_product_cost(self) -> None:
        # Default behavior, overridden in child classes
        return

    def set_allocated_cost(self, is_amortized_cost: bool, is_for_products: bool) -> None:
        # Default behavior, overridden in child classes
        if not is_for_products:
            if is_amortized_cost:
                self.amortized_cost = self.cost
            else:
                self.on_demand_cost = self.cost

    def set_cost_as_key(self, cost: float) -> None:
        # Default behavior, overridden in child classes
        return

    def set_instance_links(self, cloud_cost_allocator: 'CloudCostAllocator') -> None:
        # Default behavior, overridden in child classes
        cloud_cost_allocator.get_service_instance(self.service, self.instance).cost_items.append(self)

    def visit(self,
              visited_service_instance_list: list['ServiceInstance'],
              ignore_cost_as_key: bool,
              process_self_consumption: bool,
              is_amortized_cost: bool,
              is_for_products: bool) -> None:
        # Must be implemented in child classes
        error("Unexpected call to CostItem.visit")

    def export(self) -> dict[str]:
        # Overridden in child classes
        row = {}
        row['Date'] = self.date_str
        row['Service'] = self.service
        row['Instance'] = self.instance
        for dimension_key, dimension_value in self.dimensions.items():
            row[dimension_key] = dimension_value
        tags_str = StringIO()
        for key, value in self.tags.items():
            tags_str.write(key + ":" + value + ",")
        row['Tags'] = tags_str.getvalue()
        row['AmortizedCost'] = str(self.amortized_cost)
        row['OnDemandCost'] = str(self.on_demand_cost)
        row['Currency'] = self.currency
        return row

    def getHeaders(self) -> list[str]:
        headers = [
            'Date',
            'Service',
            'Instance'
        ]

        for dimension_key, _ in self.dimensions.items():
            headers.extend(dimension_key)
        for key, _ in self.tags.items():
            headers.extend(key)

        headers.extend('Tags')
        headers.extend('AmortizedCost')
        headers.extend('OnDemandCost')
        headers.extend('Currency')

        return headers


class CloudCostItem(CostItem):
    """
    Represents a cloud cost coming from cloud provider cost data
    """

    __slots__ = (
        'cloud_cost_line',       # type: dict[str]
        'cloud_amortized_cost',  # type: float
        'cloud_on_demand_cost',  # type: float
    )

    def __init__(self):
        CostItem.__init__(self)
        self.cloud_cost_line = {}
        self.date_str = ""
        self.cloud_amortized_cost = 0.0
        self.cloud_on_demand_cost = 0.0
        self.currency = ""

    def matches_cloud_tag_selector(self, cloud_tag_selector: str, provider_service: str) -> bool:
        eval_globals_dict = {}
        for key, value in self.tags.items():
            eval_globals_dict[re.sub(r'[^a-z0-9_]', '_', key)] = value
        match = False
        try:
            # Eval is dangerous. Considerations:
            # - Audit cost allocation keys, which are provided by DevOps
            # - Possibly forbid cloud tag selectors
            match = eval(cloud_tag_selector, eval_globals_dict, {})
        except:
            exception = sys.exc_info()[0]
            error("Caught exception '" + str(exception) +
                  "' while evaluating cloud_tag_selector '" +
                  cloud_tag_selector +
                  "' for provider service '" +
                  provider_service +
                  "'")
        return match

    def fill_from_tags(self, config: ConfigParser) -> None:

        # Service
        for service_tag_key in config['TagKey']['Service'].split(","):
            service_tag_key = service_tag_key.strip()
            if service_tag_key in self.tags:
                self.service = self.tags[service_tag_key].strip().lower()
                break
        if not self.service:
            self.service = config['General']['DefaultService'].strip()

        # Instance
        if 'Instance' in config['TagKey']:
            for instance_tag_key in config['TagKey']['Instance'].split(","):
                instance_tag_key = instance_tag_key.strip()
                if instance_tag_key in self.tags:
                    self.instance = self.tags[instance_tag_key].strip().lower()
                    break
        if not self.instance:  # Default value: same as service
            self.instance = self.service

        # Dimensions
        if 'Dimensions' in config['General']:
            for dimension in config['General']['Dimensions'].split(","):
                dimension = dimension.strip()
                for dimension_tag_key in config['TagKey'][dimension].split(","):
                    dimension_tag_key = dimension_tag_key.strip()
                    if dimension_tag_key in self.tags:
                        self.dimensions[dimension] = self.tags[dimension_tag_key].strip().lower()
                        break

    def visit(self,
              visited_service_instance_list: list['ServiceInstance'],
              ignore_cost_as_key: bool,
              process_self_consumption: bool,
              is_amortized_cost: bool,
              is_for_products: bool) -> None:
        if is_amortized_cost:
            self.cost = self.cloud_amortized_cost
        else:
            self.cost = self.cloud_on_demand_cost


class ConsumerCostItem(CostItem):
    """
    Represents a cloud cost coming from a cloud cost allocation key
    """

    __slots__ = (

        # Fields
        'provider_service',                             # type: str
        'provider_instance',                            # type: str
        'provider_tag_selector',                        # type: str
        'provider_cost_allocation_type',                # type: str
        'provider_cost_allocation_key',                 # type: float
        'provider_cost_allocation_cloud_tag_selector',  # type: str
        'provider_meter_names',                         # type: list[str]
        'provider_meter_units',                         # type: list[str]
        'provider_meter_values',                        # type: list[str]
        'product',                                      # type: str
        'product_cost',                                 # type: float
        'product_amortized_cost',                       # type: float
        'product_on_demand_cost',                       # type: float
        'product_meter_name',                           # type: str
        'product_meter_unit',                           # type: str
        'product_meter_value',                          # type: str

        # Helpers
        'provider_service_instance',  # type: ServiceInstance
    )

    def __init__(self):
        CostItem.__init__(self)
        self.provider_service = ""
        self.provider_instance = ""
        self.provider_tag_selector = ""
        self.provider_cost_allocation_type = ""
        self.provider_cost_allocation_key = 0.0
        self.provider_cost_allocation_cloud_tag_selector = ""
        self.provider_meter_names = []
        self.provider_meter_units = []
        self.provider_meter_values = []
        self.product = ""
        self.product_cost = 0.0
        self.product_amortized_cost = 0.0
        self.product_on_demand_cost = 0.0
        self.product_meter_name = ""
        self.product_meter_unit = ""
        self.product_meter_value = ""
        self.provider_service_instance = None

    def get_product(self) -> str:
        return self.product

    def get_product_meter_name(self) -> str:
        return self.product_meter_name

    def is_self_consumption(self) -> bool:
        return True if self.service == self.provider_service and self.instance == self.provider_instance else False

    def reset_product_cost(self) -> None:
        self.product_cost = 0.0

    def set_allocated_cost(self, is_amortized_cost: bool, is_for_products: bool) -> None:
        if is_for_products:
            if is_amortized_cost:
                self.product_amortized_cost = self.product_cost
            else:
                self.product_on_demand_cost = self.product_cost
        else:
            CostItem.set_allocated_cost(self, is_amortized_cost, is_for_products)

    def set_cost_as_key(self, cost: float) -> None:
        if self.provider_cost_allocation_type == "Cost":
            self.provider_cost_allocation_key = cost

    def set_instance_links(self, cloud_cost_allocator: 'CloudCostAllocator') -> None:
        CostItem.set_instance_links(self, cloud_cost_allocator)
        self.provider_service_instance = cloud_cost_allocator.get_service_instance(self.provider_service,
                                                                                   self.provider_instance)
        self.provider_service_instance.consumer_cost_items.append(self)

    def visit(self,
              visited_service_instance_list: list['ServiceInstance'],
              ignore_cost_as_key: bool,
              process_self_consumption: bool,
              is_amortized_cost: bool,
              is_for_products: bool) -> None:

        # Check self consumption
        if self.is_self_consumption() == process_self_consumption:

            # Recursively visit provider service instance
            if not self.is_self_consumption():
                self.provider_service_instance.visit(visited_service_instance_list,
                                                     ignore_cost_as_key,
                                                     is_amortized_cost,
                                                     is_for_products)

            # Ignore cost as keys
            if not (ignore_cost_as_key and self.provider_cost_allocation_type == "Cost"):

                # Compute item cost based on its provider tag selector cost
                provider_tag_selector =\
                    self.provider_service_instance.provider_tag_selector_cost_dict[self.provider_tag_selector]
                default_cost_by_product_meter = provider_tag_selector.get_or_add_default_cost_by_product_meter()
                if is_for_products:  # Product cost allocation
                    # Get key-based cost share of provider tag selector
                    if default_cost_by_product_meter.total_keys != 0.0:
                        cost = provider_tag_selector.adjusted_cost * self.provider_cost_allocation_key /\
                               default_cost_by_product_meter.total_keys
                    else:
                        cost = provider_tag_selector.adjusted_cost / default_cost_by_product_meter.nb_keys
                else:  # Service cost allocation
                    # Get key-based cost share of default product
                    if default_cost_by_product_meter.total_keys != 0.0:
                        cost = default_cost_by_product_meter.adjusted_cost * self.provider_cost_allocation_key /\
                               default_cost_by_product_meter.total_keys
                    else:
                        cost = default_cost_by_product_meter.adjusted_cost / default_cost_by_product_meter.nb_keys

                    # Get key-based cost share of own product if any
                    if self.product:
                        cost_by_product_meter =\
                            provider_tag_selector.get_or_add_cost_by_product_meter(self.product,
                                                                                   self.product_meter_name)
                        if cost_by_product_meter.total_keys != 0.0:
                            cost += cost_by_product_meter.adjusted_cost * self.provider_cost_allocation_key /\
                                    cost_by_product_meter.total_keys
                        else:
                            cost += cost_by_product_meter.adjusted_cost / cost_by_product_meter.nb_keys

                # Set cost
                if is_for_products and self.product:
                    # Cost goes to product
                    # In the sequel of the visit, this cost will not be allocated to the consumers of
                    # the instance (containing this item), as costs must be allocated only once to products
                    self.product_cost = cost
                else:
                    # Cost goes to item, and so to the instance containing this item
                    self.cost = cost

    def export(self) -> dict[str]:
        row = super().export()
        row['ProviderService'] = self.provider_service
        row['ProviderInstance'] = self.provider_instance
        row['ProviderTagSelector'] = self.provider_tag_selector
        row['ProviderCostAllocationType'] = self.provider_cost_allocation_type
        row['ProviderCostAllocationKey'] = str(self.provider_cost_allocation_key)
        row['ProviderCostAllocationCloudTagSelector'] = self.provider_cost_allocation_cloud_tag_selector
        index = 0
        for provider_meter_name in self.provider_meter_names:
            row['ProviderMeterName%s' % (index+1)] = provider_meter_name
            index += 1
        index = 0
        for provider_meter_unit in self.provider_meter_units:
            row['ProviderMeterUnit%s' % (index + 1)] = provider_meter_unit
            index += 1
        index = 0
        for provider_meter_value in self.provider_meter_values:
            row['ProviderMeterValue%s' % (index + 1)] = provider_meter_value
            index += 1
        row['Product'] = self.product
        if self.product:
            row['ProductAmortizedCost'] = self.product_amortized_cost
            row['ProductOnDemandCost'] = self.product_on_demand_cost
        row['ProductMeterName'] = self.product_meter_name
        row['ProductMeterUnit'] = self.product_meter_unit
        row['ProductMeterValue'] = self.product_meter_value
        return row

    def getHeaders(self) -> list[str]:
        headers = [
            'Date',
            'ProviderService',
            'ProviderInstance',
            'ProviderTagSelector',
            'ProviderMeterName1',
            'ProviderMeterUnit1',
            'ProviderMeterValue1',
            'ProviderMeterName2',
            'ProviderMeterUnit2',
            'ProviderMeterValue2',
            'ProviderMeterName3',
            'ProviderMeterUnit3',
            'ProviderMeterValue3',
            'ProviderMeterName4',
            'ProviderMeterUnit4',
            'ProviderMeterValue4',
            'ProviderMeterName5',
            'ProviderMeterUnit5',
            'ProviderMeterValue5',
            'ProviderCostAllocationType',
            'ProviderCostAllocationKey',
            'ProviderCostAllocationCloudTagSelector',
            'ConsumerService',
            'ConsumerInstance',
            'ConsumerTags',
            'Product',
            'ProductMeterName',
            'ProductMeterUnit',
            'ProductMeterValue',
        ]

        # Add dimensions
        if 'Dimensions' in self.config['General']:
            for dimension in self.config['General']['Dimensions'].split(","):
                headers.extend(['Consumer' + dimension.strip()])

        return headers

class CostItemFactory(object):
    """"
    Creates Cost Items
    """

    def create_cloud_cost_item(self) -> CloudCostItem:
        return CloudCostItem()

    def create_consumer_cost_item(self) -> ConsumerCostItem:
        return ConsumerCostItem()


class ProviderTagSelectorCostByProductMeter(object):
    """
    Represents the cost allocated for a given provider tag selector for a given product
    """

    __slots__ = (
        'product',             # type: str
        'product_meter_name',  # type: str
        'raw_cost',            # type: float
        'adjusted_cost',       # type: float
        'total_keys',          # type: float
        'nb_keys'              # type: float
    )

    def __init__(self, product, product_meter_name):
        self.product = product
        self.product_meter_name = product_meter_name
        self.raw_cost = 0.0
        self.adjusted_cost = 0.0
        self.total_keys = 0.0
        self.nb_keys = 0.0

    @staticmethod
    def get_product_meter_id(product: str, product_meter_name: str) -> str:
        return product + "." + product_meter_name

    def is_default(self) -> bool:
        return True if len(self.product) == 0 and len(self.product_meter_name) == 0 else False


class ProviderTagSelectorCost(object):
    """
    Represents the cost allocated for a given provider tag selector
    """

    __slots__ = (
        'selector',                 # type: str
        'raw_cost',                 # type: float
        'adjusted_cost',            # type: float
        'costs_by_product_meter',   # type: dict[ProviderTagSelectorCostByProductMeter]
    )

    def __init__(self, selector):
        self.selector = selector
        self.raw_cost = 0.0
        self.adjusted_cost = 0.0
        self.costs_by_product_meter = {}

    def get_or_add_cost_by_product_meter(self,
                                         product: str,
                                         product_meter_name: str) -> ProviderTagSelectorCostByProductMeter:
        product_meter_id =\
            ProviderTagSelectorCostByProductMeter.get_product_meter_id(product, product_meter_name)
        if product_meter_id not in self.costs_by_product_meter:
            self.costs_by_product_meter[product_meter_id] = ProviderTagSelectorCostByProductMeter(product,
                                                                                                  product_meter_name)
        return self.costs_by_product_meter[product_meter_id]

    def get_or_add_default_cost_by_product_meter(self) -> ProviderTagSelectorCostByProductMeter:
        return self.get_or_add_cost_by_product_meter('', '')

    def has_cost_by_product_meter(self, product: str, product_meter_name: str) -> bool:
        product_meter_id =\
            ProviderTagSelectorCostByProductMeter.get_product_meter_id(product, product_meter_name)
        return True if product_meter_id in self.costs_by_product_meter else False

    def is_default(self) -> bool:
        return True if len(self.selector) == 0 else False

    def update_costs_by_product_meter_raw_cost(self, provider_cost_item: CostItem) -> None:
        product = provider_cost_item.get_product()
        product_meter_name = provider_cost_item.get_product_meter_name()
        if self.has_cost_by_product_meter(product, product_meter_name):
            cost_by_product_meter = self.get_or_add_cost_by_product_meter(product, product_meter_name)
        else:
            cost_by_product_meter = self.get_or_add_default_cost_by_product_meter()
        cost_by_product_meter.raw_cost += provider_cost_item.cost


class ServiceInstance(object):
    """
    Represents the instance of a service
    """

    __slots__ = (

        # Identifiers
        'service',   # type: str
        'instance',  # type: str

        # Lists of items and consumer items
        'cost_items',           # type: list[CostItem]
        'consumer_cost_items',  # type: list[ConsumerCostItem]

        # Cost and flags for the visit algorithm
        'cost',              # type: float
        'is_visited',        # type: bool
        'is_being_visited',  # type: bool
        
        # The dictionary from provider tag selectors to their costs for this service instance
        'provider_tag_selector_cost_dict',   # type: dict[str,ProviderTagSelectorCost]
    )

    def __init__(self, service: str, instance: str):
        self.service = service
        self.instance = instance
        self.cost_items = []
        self.consumer_cost_items = []
        self.cost = 0.0
        self.is_visited = False
        self.is_being_visited = False
        self.provider_tag_selector_cost_dict = {}

    def compute_provider_tag_selector_costs(self) -> None:

        # Check if this service instance is a provider
        if not self.consumer_cost_items:
            return

        # Initiate provider tag selector costs and costs by product meter, by processing consumer items
        self.provider_tag_selector_cost_dict = {}
        for consumer_item in self.consumer_cost_items:

            # Create provider tag selector if does not exist yet
            if consumer_item.provider_tag_selector not in self.provider_tag_selector_cost_dict:
                self.provider_tag_selector_cost_dict[consumer_item.provider_tag_selector] = \
                    ProviderTagSelectorCost(consumer_item.provider_tag_selector)
            provider_tag_selector_cost = self.provider_tag_selector_cost_dict[consumer_item.provider_tag_selector]

            # Update keys of default cost by product meter, which concerns all consumers with this provider tag selector
            default_cost_by_product_meter = provider_tag_selector_cost.get_or_add_default_cost_by_product_meter()
            default_cost_by_product_meter.total_keys += consumer_item.provider_cost_allocation_key
            default_cost_by_product_meter.nb_keys += 1

            # Update key of cost by product meter, if consumer has a product
            if consumer_item.product:
                cost_by_product_meter =\
                    provider_tag_selector_cost.get_or_add_cost_by_product_meter(consumer_item.product,
                                                                                consumer_item.product_meter_name)
                cost_by_product_meter.total_keys += consumer_item.provider_cost_allocation_key
                cost_by_product_meter.nb_keys += 1

        # Reset the number of matching provider tag selectors of every item
        for item in self.cost_items:
            item.nb_matching_provider_tag_selectors = 0

        # Compute raw costs of non-default provider tag selectors, by checking matching items
        total_provider_tag_selector_raw_cost = 0.0
        for provider_tag_selector_cost in self.provider_tag_selector_cost_dict.values():
            if not provider_tag_selector_cost.is_default():
                for item in self.cost_items:

                    # Check if item matches provider tag selector
                    eval_globals_dict = {}
                    for key, value in item.tags.items():
                        eval_globals_dict[re.sub(r'[^a-z0-9_]', '_', key)] = value
                    eval_true = False
                    try:
                        # Eval is dangerous. Considerations:
                        # - Audit cost allocation keys, which are provided by DevOps
                        # - Possibly forbid provider tag selectors
                        eval_true = eval(provider_tag_selector_cost.selector, eval_globals_dict, {})
                    except:
                        exception = sys.exc_info()[0]
                        error("Caught exception '" + str(exception) +
                              "' while evaluating provider tag selector '" +
                              provider_tag_selector_cost.selector +
                              "' for provider service '" +
                              self.service +
                              "'")

                    # If item matches provider tag selector, update raw costs
                    if eval_true:
                        item.nb_matching_provider_tag_selectors += 1
                        provider_tag_selector_cost.raw_cost += item.cost
                        total_provider_tag_selector_raw_cost += item.cost
                        provider_tag_selector_cost.update_costs_by_product_meter_raw_cost(item)

        # Compute the raw cost of the default provider tag selector
        if '' in self.provider_tag_selector_cost_dict:
            default_provider_tag_selector = self.provider_tag_selector_cost_dict['']
            for item in self.cost_items:
                if item.nb_matching_provider_tag_selectors == 0:
                    item.nb_matching_provider_tag_selectors = 1
                    default_provider_tag_selector.raw_cost += item.cost
                    total_provider_tag_selector_raw_cost += item.cost
                    default_provider_tag_selector.update_costs_by_product_meter_raw_cost(item)

        # Check if provider tag selectors form a partition
        is_partition = True
        for item in self.cost_items:
            if item.nb_matching_provider_tag_selectors != 1:
                is_partition = False

        # For info
        if not is_partition:
            info("Provider tag selectors of provider service instance " +
                 self.service + "." + self.instance +
                 " do not form a partition")

        # Adjust costs
        for provider_tag_selector_cost in self.provider_tag_selector_cost_dict.values():

            # Adjust provider tag selector cost
            if is_partition:
                # I love it when a plan comes together
                provider_tag_selector_cost.adjusted_cost = provider_tag_selector_cost.raw_cost
            elif total_provider_tag_selector_raw_cost != 0.0:
                # Adjust proportionally
                provider_tag_selector_cost.adjusted_cost =\
                    self.cost * provider_tag_selector_cost.raw_cost / total_provider_tag_selector_raw_cost

            else:
                # Adjust equally
                provider_tag_selector_cost.adjusted_cost = self.cost / len(self.provider_tag_selector_cost_dict)

            # Adjust costs by product meter
            for cost_by_product_meter in provider_tag_selector_cost.costs_by_product_meter.values():
                if provider_tag_selector_cost.raw_cost != 0.0:
                    # Adjust proportionally
                    cost_by_product_meter.adjusted_cost = cost_by_product_meter.raw_cost *\
                                                          provider_tag_selector_cost.adjusted_cost /\
                                                          provider_tag_selector_cost.raw_cost
                else:
                    # Adjust equally
                    cost_by_product_meter.adjusted_cost = provider_tag_selector_cost.adjusted_cost /\
                                                          len(provider_tag_selector_cost.costs_by_product_meter)

    @staticmethod
    def get_id(service: str, instance: str) -> str:
        return service + '.' + instance

    def get_self_id(self) -> str:
        return ServiceInstance.get_id(self.service, self.instance)

    def reset_visit(self, is_for_products: bool) -> None:
        self.cost = 0.0
        self.is_visited = False
        self.is_being_visited = False
        for item in self.cost_items:
            item.reset_cost()
            if is_for_products:
                item.reset_product_cost()

    def visit(self,
              visited_service_instance_list: list['ServiceInstance'],
              ignore_cost_as_key: bool,
              is_amortized_cost: bool,
              is_for_products: bool) -> None:

        # Already visited?
        if self.is_visited:
            return

        # Cyclic cost allocation?
        # TODO: break the cycle before the cost allocation
        if self.is_being_visited:
            message = StringIO()
            message.write("Cyclic cost allocation detected: ")
            for visited_service_instance in visited_service_instance_list:
                message.write(visited_service_instance.get_self_id() + ",")
            message.write(self.get_self_id())
            info(message.getvalue())
            self.is_visited = True
            return

        # Set being visited
        self.is_being_visited = True
        visited_service_instance_list.append(self)

        # visit items, except self-consumption, and update cost
        for item in self.cost_items:
            item.visit(visited_service_instance_list, ignore_cost_as_key, False, is_amortized_cost, is_for_products)
            self.cost += item.cost

        # Compute provider tag selector costs
        self.compute_provider_tag_selector_costs()

        # visit self-consumption
        for item in self.cost_items:
            item.visit(visited_service_instance_list, ignore_cost_as_key, True, is_amortized_cost, is_for_products)

        # Set visited
        self.is_visited = True


class CloudCostAllocator(object):
    """
    Allocates cloud costs from a cloud cost reader and cost allocation key readers
    """

    __slots__ = (
        'config',             # type: ConfigParser
        'cost_item_factory',  # type: CostItemFactory
        'service_instances',  # type: dict[ServiceInstance]
    )

    def __init__(self, cost_item_factory: CostItemFactory, config: ConfigParser):
        self.config = config
        self.cost_item_factory = cost_item_factory
        self.service_instances = {}

    def allocate(self, consumer_cost_items: list[ConsumerCostItem], cloud_cost_items: list[CloudCostItem]) -> bool:

        # Create the list of all cost items and process cloud tag selectors
        cost_items = []
        cost_items.extend(cloud_cost_items)
        for consumer_cost_item in consumer_cost_items:
            if consumer_cost_item.provider_cost_allocation_type == "CloudTagSelector":
                self.process_cloud_tag_selector(cost_items, consumer_cost_item, cloud_cost_items)
            else:
                cost_items.append(consumer_cost_item)

        # Create and add cloud consumer cost item from tags
        new_consumer_cost_items = []
        self.create_consumer_cost_items_from_tags(new_consumer_cost_items, cost_items)
        cost_items.extend(new_consumer_cost_items)

        # Check all dates are the same
        date_str = ""
        for cost_item in cost_items:
            if cost_item.date_str:
                date_str = cost_item.date_str
        for cost_item in cost_items:
            if date_str != cost_item.date_str:
                error("Found cost items with different dates: " + date_str + " and " + cost_item.date_str)
                d = cost_item.export()
                error(str(d))
                return False

        # Check all currencies are the same and populate missing ones (currencies are missing for consumer
        # cost items)
        currency = ""
        for cost_item in cost_items:
            if cost_item.currency:
                currency = cost_item.currency
        for cost_item in cost_items:
            if not cost_item.currency:
                cost_item.currency = currency
            else:
                if currency != cost_item.currency:
                    error("Found cost items with different currencies: " + currency + " and " + cost_item.currency)
                    return False

        # Initialize instances and set cost item links
        self.service_instances = {}
        for cost_item in cost_items:
            cost_item.set_instance_links(self)

        # Compute service amortized cost, ignoring the keys that are using cost, and then
        # set these keys from the computed cost
        self.visit(True, True, False)
        for service_instance in self.service_instances.values():
            for cost_item in service_instance.cost_items:
                cost_item.set_cost_as_key(service_instance.cost)

        # Allocate amortized costs for services
        self.visit_and_set_allocated_cost(True, False)

        # Allocate on-demand costs for services
        self.visit_and_set_allocated_cost(False, False)

        # Allocate amortized costs for products
        self.visit_and_set_allocated_cost(True, True)

        # Allocate on-demand costs for products
        self.visit_and_set_allocated_cost(False, True)

        return True

    def create_consumer_cost_items_from_tags(self,
                                             new_consumer_cost_items: list[ConsumerCostItem],
                                             cost_items: list[CostItem]) -> None:

        # Check if consumer tag is used and process cost items
        if 'ConsumerService' in self.config['TagKey']:
            for cost_item in cost_items:

                # Check consumer service
                consumer_service = ""
                actual_consumer_service_tag_key = ""
                for consumer_service_tag_key in self.config['TagKey']['ConsumerService'].split(","):
                    consumer_service_tag_key = consumer_service_tag_key.strip()
                    if consumer_service_tag_key in cost_item.tags:
                        actual_consumer_service_tag_key = consumer_service_tag_key
                        consumer_service = cost_item.tags[consumer_service_tag_key].strip().lower()
                        break
                if consumer_service == "-": # Ignore consumer service named "-"
                    consumer_service = ""

                # Check consumer instance
                consumer_instance = ""
                actual_consumer_instance_tag_key = ""
                if 'ConsumerInstance' in self.config['TagKey']:
                    for consumer_instance_tag_key in self.config['TagKey']['ConsumerInstance'].split(","):
                        consumer_instance_tag_key = consumer_instance_tag_key.strip()
                        if consumer_instance_tag_key in cost_item.tags:
                            actual_consumer_instance_tag_key = consumer_instance_tag_key
                            consumer_instance = cost_item.tags[consumer_instance_tag_key].strip().lower()
                            break

                # Check product
                product = ""
                actual_product_tag_key = ""
                if 'Product' in self.config['TagKey']:
                    for product_tag_key in self.config['TagKey']['Product'].split(","):
                        product_tag_key = product_tag_key.strip()
                        if product_tag_key in cost_item.tags:
                            actual_product_tag_key = product_tag_key
                            product = cost_item.tags[product_tag_key].strip().lower()
                            break

                # Create consumer cost item if there is a consumer service or product
                if consumer_service or product:

                    # Set consumer service
                    if not consumer_service:
                        # Product tag exists: set self-consumption, to materialize final consumption
                        consumer_service = cost_item.service

                    # Set consumer instance
                    if not consumer_instance:
                        # Same as service by default
                        consumer_instance = consumer_service

                    # Create cloud consumer cost item
                    new_consumer_cost_item = self.cost_item_factory.create_consumer_cost_item()
                    new_consumer_cost_item.service = consumer_service
                    new_consumer_cost_item.instance = consumer_instance
                    new_consumer_cost_item.date_str = cost_item.date_str
                    new_consumer_cost_item.provider_service = cost_item.service
                    new_consumer_cost_item.provider_instance = cost_item.instance
                    new_consumer_cost_item.provider_tag_selector = ""
                    if actual_consumer_service_tag_key:
                        new_consumer_cost_item.provider_tag_selector =\
                            "'" + actual_consumer_service_tag_key + "' in globals() and " +\
                            actual_consumer_service_tag_key + "=='" + consumer_service + "'"
                        if actual_consumer_instance_tag_key:
                            new_consumer_cost_item.provider_tag_selector +=\
                                " and '" + actual_consumer_instance_tag_key + "' in globals() and " +\
                                actual_consumer_instance_tag_key + "=='" + consumer_instance + "'"
                    if actual_product_tag_key:
                        if new_consumer_cost_item.provider_tag_selector:
                            new_consumer_cost_item.provider_tag_selector += " and "
                        new_consumer_cost_item.provider_tag_selector +=\
                            "'" + actual_product_tag_key + "' in globals() and " +\
                            actual_product_tag_key + "=='" + product + "'"
                    new_consumer_cost_item.provider_cost_allocation_type = "ConsumerTag"
                    new_consumer_cost_item.provider_cost_allocation_key = 1.0
                    new_consumer_cost_item.product = product

                    # Add consumer dimensions
                    if 'Dimensions' in self.config['General']:
                        for dimension in self.config['General']['Dimensions'].split(','):
                            consumer_dimension = 'Consumer' + dimension.strip()
                            if consumer_dimension in self.config['TagKey']:
                                for consumer_dimension_tag_key in self.config['TagKey'][consumer_dimension].split(","):
                                    if consumer_dimension_tag_key in cost_item.tags:
                                        new_consumer_cost_item.dimensions[dimension] =\
                                            cost_item.tags[consumer_dimension_tag_key].strip().lower()
                                        break

                    # Add cloud consumer cost item
                    new_consumer_cost_items.append(new_consumer_cost_item)

    def get_service_instance(self, service: str, instance: str) -> ServiceInstance:
        service_instance_id = ServiceInstance.get_id(service, instance)
        if service_instance_id not in self.service_instances:  # Create service instance if not existing yet
            service_instance = ServiceInstance(service, instance)
            self.service_instances[service_instance_id] = service_instance
        return self.service_instances[service_instance_id]

    def process_cloud_tag_selector(self,
                                   cost_items: list[CostItem],
                                   consumer_cost_item: ConsumerCostItem,
                                   cloud_cost_items: list[CloudCostItem]) -> None:

        # Process cost items
        new_consumer_cost_items = {}  # Key is consumer service instance id
        for cloud_cost_item in cloud_cost_items:

            # Skip if same service: cost allocation to own service is unwanted
            # Check if cloud selector match
            consumer_service_instance_id = ServiceInstance.get_id(cloud_cost_item.service, cloud_cost_item.instance)
            cloud_tag_selector = consumer_cost_item.provider_cost_allocation_cloud_tag_selector
            if cloud_cost_item.service != consumer_cost_item.provider_service and\
                    cloud_cost_item.matches_cloud_tag_selector(cloud_tag_selector, consumer_cost_item.provider_service):

                # Check if matching service instance was already processed
                if consumer_service_instance_id in new_consumer_cost_items:

                    # Increase existing cost allocation key with the amortized cost of this cloud cost item
                    new_consumer_cost_item = new_consumer_cost_items[consumer_service_instance_id]
                    new_consumer_cost_item.provider_cost_allocation_key += cloud_cost_item.cloud_amortized_cost

                else:
                    # Create new consumer cost item for this instance
                    new_consumer_cost_item = self.cost_item_factory.create_consumer_cost_item()
                    new_consumer_cost_item.date_str = cloud_cost_item.date_str
                    new_consumer_cost_item.service = cloud_cost_item.service
                    new_consumer_cost_item.instance = cloud_cost_item.instance
                    new_consumer_cost_item.tags = new_consumer_cost_item.tags.copy()
                    new_consumer_cost_item.provider_service = consumer_cost_item.provider_service
                    new_consumer_cost_item.provider_instance = consumer_cost_item.provider_instance
                    new_consumer_cost_item.provider_meter_names = consumer_cost_item.provider_meter_names.copy()
                    # TODO: split and dispatch the provider meter values based on amortized costs
                    new_consumer_cost_item.provider_meter_values = consumer_cost_item.provider_meter_values.copy()
                    new_consumer_cost_item.provider_meter_units = consumer_cost_item.provider_meter_units.copy()
                    new_consumer_cost_item.provider_cost_allocation_type =\
                        consumer_cost_item.provider_cost_allocation_type
                    new_consumer_cost_item.provider_tag_selector = consumer_cost_item.provider_tag_selector
                    new_consumer_cost_item.provider_cost_allocation_key = cloud_cost_item.cloud_amortized_cost
                    new_consumer_cost_item.provider_cost_allocation_cloud_tag_selector =\
                        consumer_cost_item.provider_cost_allocation_cloud_tag_selector

                    # Add new consumer cost item
                    new_consumer_cost_items[consumer_service_instance_id] = new_consumer_cost_item
                    cost_items.append(new_consumer_cost_item)

    def read(self, cost_items: list[ConsumerCostItem], cost_items_in) -> None:
        # Read lines
        for line in cost_items_in:

            # Create item
            consumer_cost_item = self.cost_item_factory.create_consumer_cost_item()

            # Populate item
            consumer_cost_item.date_str = line['Date'].strip()
            if 'ProviderService' in line:
                consumer_cost_item.provider_service = line['ProviderService'].lower()
            if not consumer_cost_item.provider_service:
                error("Skipping cost allocation key line without ProviderService")
                continue
            if 'ProviderInstance' in line:
                consumer_cost_item.provider_instance = line['ProviderInstance'].lower()
            if not consumer_cost_item.provider_instance:
                consumer_cost_item.provider_instance = consumer_cost_item.provider_service  # Default value
            if 'Product' in line:
                consumer_cost_item.product = line['Product'].lower()
            if 'ProductMeterName' in line:
                consumer_cost_item.product_meter_name = line['ProductMeterName']
            if 'ProductMeterUnit' in line:
                consumer_cost_item.product_meter_unit = line['ProductMeterUnit']
            if 'ProductMeterValue' in line:
                consumer_cost_item.product_meter_value = line['ProductMeterValue']
            if 'ConsumerService' in line:
                consumer_cost_item.service = line['ConsumerService'].lower()
            if 'ConsumerInstance' in line:
                consumer_cost_item.instance = line['ConsumerInstance'].lower()
            # Set default values for service and instance
            if not consumer_cost_item.service:
                if consumer_cost_item.product:  # Set self-consumption, to materialize final consumption
                    consumer_cost_item.service = consumer_cost_item.provider_service
                    consumer_cost_item.instance = consumer_cost_item.provider_instance
                else:  # Garbage collector
                    consumer_cost_item.service = self.config['General']['DefaultService'].strip()
                    consumer_cost_item.instance = consumer_cost_item.service
            elif not consumer_cost_item.instance:  # Same as service by default
                consumer_cost_item.instance = consumer_cost_item.service
            if 'Dimensions' in self.config['General']:
                for dimension in self.config['General']['Dimensions'].split(','):
                    consumer_dimension = 'Consumer' + dimension.strip()
                    if consumer_dimension in line:
                        consumer_cost_item.dimensions[dimension] = line[consumer_dimension].lower()
            if 'ConsumerTags' in line:
                consumer_tags = line["ConsumerTags"]
                if consumer_tags:
                    tags = consumer_tags.split(',')
                    for tag in tags:
                        if tag:
                            key_value_match = re.match("([^:]+):([^:]*)", tag)
                            if key_value_match:
                                key = key_value_match.group(1).strip().lower()
                                value = key_value_match.group(2).strip().lower()
                                consumer_cost_item.tags[key] = value
                            else:
                                error("Unexpected consumer tag format: '" + tag + "'")
            if 'NumberOfProviderMeters' in self.config['General']:
                nb_provider_meters = int(self.config['General']['NumberOfProviderMeters'])
                for i in range(nb_provider_meters):
                    provider_meter_name = ''
                    if 'ProviderMeterName%d' % (i + 1) in line:
                        provider_meter_name = line['ProviderMeterName%d' % (i + 1)]
                    consumer_cost_item.provider_meter_names.append(provider_meter_name)
                    provider_meter_unit = ''
                    if 'ProviderMeterUnit%d' % (i + 1) in line:
                        provider_meter_unit = line['ProviderMeterUnit%d' % (i + 1)]
                    consumer_cost_item.provider_meter_units.append(provider_meter_unit)
                    provider_meter_value = ''
                    if 'ProviderMeterValue%d' % (i + 1) in line:
                        provider_meter_value_column = 'ProviderMeterValue%d' % (i + 1)
                        provider_meter_value = line[provider_meter_value_column]
                        if provider_meter_value:
                            try:
                                float(provider_meter_value)
                            except (TypeError, ValueError):
                                error("Value '" + provider_meter_value + "' of '" + provider_meter_value_column +
                                      "' of ProviderService '" + consumer_cost_item.provider_service + "'" +
                                      "is not a float")
                    consumer_cost_item.provider_meter_values.append(provider_meter_value)

            consumer_cost_item.provider_cost_allocation_type = "Key"  # Default value
            if 'ProviderCostAllocationType' in line:
                consumer_cost_item.provider_cost_allocation_type = line['ProviderCostAllocationType']
                if consumer_cost_item.provider_cost_allocation_type not in ("Key", "Cost", "CloudTagSelector"):
                    error("Unknown ProviderCostAllocationType '" + consumer_cost_item.provider_cost_allocation_type +
                          "' for ProviderService '" + consumer_cost_item.provider_service + "'")
                    continue
            if consumer_cost_item.provider_cost_allocation_type == 'Key':
                key_str = ""
                if 'ProviderCostAllocationKey' in line and line['ProviderCostAllocationKey']:
                    try:
                        key_str = line['ProviderCostAllocationKey']
                        consumer_cost_item.provider_cost_allocation_key = float(key_str)
                    except (TypeError, ValueError):
                        pass
                if consumer_cost_item.provider_cost_allocation_key == 0.0:
                    error("Skipping cost allocation key line with non-float " +
                          " ProviderCostAllocationKey: '" + key_str + "'" +
                          " for ProviderService '" + consumer_cost_item.provider_service + "'")
                    continue
            elif consumer_cost_item.provider_cost_allocation_type == "CloudTagSelector":
                if 'ProviderCostAllocationCloudTagSelector' in line:
                    consumer_cost_item.provider_cost_allocation_cloud_tag_selector =\
                        line['ProviderCostAllocationCloudTagSelector']
            if "ProviderTagSelector" in line:
                consumer_cost_item.provider_tag_selector = line["ProviderTagSelector"].lower()

            # Add item
            cost_items.append(consumer_cost_item)
    
    def visit_and_set_allocated_cost(self, is_amortized_cost: bool, is_for_products: bool) -> None:

        # Visit, using cost keys, which have been previously computed
        self.visit(False, is_amortized_cost, is_for_products)

        # Set allocated costs
        for service_instance in self.service_instances.values():
            for cost_item in service_instance.cost_items:
                cost_item.set_allocated_cost(is_amortized_cost, is_for_products)

    def visit(self, ignore_cost_as_key: bool, is_amortized_cost: bool, is_for_products: bool) -> None:
        for service_instance in self.service_instances.values():
            service_instance.reset_visit(is_for_products)
        for service_instance in self.service_instances.values():
            visited_service_instance_list = []
            service_instance.visit(visited_service_instance_list, ignore_cost_as_key, is_amortized_cost, is_for_products)

    def write(self, writer) -> None:
        # Process cost items ordered by service instance
        for service_instance_id in sorted(self.service_instances.keys()):
            service_instance = self.service_instances[service_instance_id]
            for cost_item in service_instance.cost_items:
                # Write fields
                row = cost_item.export()
                writer.writerow(row)

    def getHeaders(self) -> list[str]:
        headers = [
            'Date',
            'Service',
            'Instance',
            'Tags',
            'AmortizedCost',
            'OnDemandCost',
            'Currency',
            'ProviderService',
            'ProviderInstance',
            'ProviderTagSelector',
            'ProviderCostAllocationType',
            'ProviderCostAllocationKey',
            'ProviderCostAllocationCloudTagSelector',
            'Product',
            'ProductAmortizedCost',
            'ProductOnDemandCost',
            'ProductMeterName',
            'ProductMeterUnit',
            'ProductMeterValue'
        ]

        # Add dimensions
        if 'Dimensions' in self.config['General']:
            for dimension in self.config['General']['Dimensions'].split(","):
                headers.extend([dimension.strip()])

        # Add provider meters
        if 'NumberOfProviderMeters' in self.config['General']:
            for index in range(int(self.config['General']['NumberOfProviderMeters'])):
                headers.extend(['ProviderMeterName%s' % (index + 1)])
                headers.extend(['ProviderMeterUnit%s' % (index + 1)])
                headers.extend(['ProviderMeterValue%s' % (index + 1)])

        return headers

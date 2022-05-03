# coding: utf-8

from abc import ABC, abstractmethod
from configparser import ConfigParser
from io import StringIO
from logging import info, error
import re
import sys

from cloud_cost_allocation.exceptions import CycleException, BreakableCycleException, UnbreakableCycleException


class CostItem(ABC):
    """
    Represents a cost item, which comes either from the cloud or from a cost allocation key
    """

    __slots__ = (
        # Fields
        'date_str',        # type: str
        'service',         # type: str
        'instance',        # type: str
        'dimensions',      # type: dict[str,str]
        'tags',            # type: dict[str,str]
        'amortized_cost',  # type: float
        'on_demand_cost',  # type: float
        'currency',        # type: str

        # Helpers
        'cost',                                # type: float
        'nb_matching_provider_tag_selectors',  # type: int
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

    def get_consumer_cost_item_provider_service_instance(self) -> 'ServiceInstance':
        # Default behavior, overridden in child classes
        return None

    def get_product(self) -> str:
        # Default behavior, overridden in child classes
        return ''

    def get_product_meter_name(self) -> str:
        # Default behavior, overridden in child classes
        return ''

    def is_consumer_cost_item_removed_for_cycle(self) -> bool:
        # Default behavior, overridden in child classes
        return False

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

    # Must be implemented in child classes
    @abstractmethod
    def visit_for_allocation(self,
                             visited_service_instance_list: list['ServiceInstance'],
                             ignore_cost_as_key: bool,
                             process_self_consumption: bool,
                             is_amortized_cost: bool,
                             is_for_products: bool) -> None:
        pass

    # Must be implemented in child classes
    @abstractmethod
    def visit_for_cycles(self,
                         visited_service_instance_list: list['ServiceInstance'],
                         service_precedence_list: list[str]) -> None:
        pass


class CloudCostItem(CostItem):
    """
    Represents a cloud cost coming from cloud provider cost data
    """

    __slots__ = (
        'cloud_amortized_cost',  # type: float
        'cloud_on_demand_cost',  # type: float
    )

    def __init__(self):
        super().__init__()
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

    def visit_for_allocation(self,
                             visited_service_instance_list: list['ServiceInstance'],
                             ignore_cost_as_key: bool,
                             process_self_consumption: bool,
                             is_amortized_cost: bool,
                             is_for_products: bool) -> None:
        if is_amortized_cost:
            self.cost = self.cloud_amortized_cost
        else:
            self.cost = self.cloud_on_demand_cost

    def visit_for_cycles(self,
                         visited_service_instance_list: list['ServiceInstance'],
                         service_precedence_list: list[str]) -> None:
        # Nothing to do
        return


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
        'provider_meters',                              # type: list[dict[str,str]]
        'product',                                      # type: str
        'product_cost',                                 # type: float
        'product_amortized_cost',                       # type: float
        'product_on_demand_cost',                       # type: float
        'product_meter_name',                           # type: str
        'product_meter_unit',                           # type: str
        'product_meter_value',                          # type: str

        # Helpers
        'is_removed_from_cycle',      # type: bool
        'provider_service_instance',  # type: ServiceInstance
    )

    def __init__(self):
        super().__init__()
        self.provider_service = ""
        self.provider_instance = ""
        self.provider_tag_selector = ""
        self.provider_cost_allocation_type = ""
        self.provider_cost_allocation_key = 0.0
        self.provider_cost_allocation_cloud_tag_selector = ""
        self.provider_meters = []
        self.product = ""
        self.product_cost = 0.0
        self.product_amortized_cost = 0.0
        self.product_on_demand_cost = 0.0
        self.product_meter_name = ""
        self.product_meter_unit = ""
        self.product_meter_value = ""
        self.is_removed_from_cycle = False
        self.provider_service_instance = None

    def get_consumer_cost_item_provider_service_instance(self) -> 'ServiceInstance':
        return self.provider_service_instance

    def get_product(self) -> str:
        return self.product

    def get_product_meter_name(self) -> str:
        return self.product_meter_name

    def is_consumer_cost_item_removed_for_cycle(self) -> bool:
        return self.is_removed_from_cycle

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
            super().set_allocated_cost(is_amortized_cost, is_for_products)

    def set_cost_as_key(self, cost: float) -> None:
        if self.provider_cost_allocation_type == "Cost":
            self.provider_cost_allocation_key = cost

    def set_instance_links(self, cloud_cost_allocator: 'CloudCostAllocator') -> None:
        super().set_instance_links(cloud_cost_allocator)
        self.provider_service_instance = cloud_cost_allocator.get_service_instance(self.provider_service,
                                                                                   self.provider_instance)
        self.provider_service_instance.consumer_cost_items.append(self)

    def visit_for_allocation(self,
                             visited_service_instance_list: list['ServiceInstance'],
                             ignore_cost_as_key: bool,
                             process_self_consumption: bool,
                             is_amortized_cost: bool,
                             is_for_products: bool) -> None:

        # Check self consumption
        if self.is_self_consumption() == process_self_consumption:

            # Recursively visit provider service instance
            if not self.is_self_consumption():
                self.provider_service_instance.visit_for_allocation(visited_service_instance_list,
                                                                    ignore_cost_as_key,
                                                                    is_amortized_cost,
                                                                    is_for_products)

            # Ignore cost as keys
            if not (ignore_cost_as_key and self.provider_cost_allocation_type == "Cost"):

                # Compute item cost based on its provider tag selector cost
                provider_tag_selector = \
                    self.provider_service_instance.provider_tag_selector_cost_dict[self.provider_tag_selector]
                default_cost_by_product_meter = provider_tag_selector.get_or_add_default_cost_by_product_meter()
                if is_for_products:  # Product cost allocation
                    # Get key-based cost share of provider tag selector
                    if default_cost_by_product_meter.total_keys != 0.0:
                        cost = provider_tag_selector.adjusted_cost * self.provider_cost_allocation_key / \
                               default_cost_by_product_meter.total_keys
                    else:
                        cost = provider_tag_selector.adjusted_cost / default_cost_by_product_meter.nb_keys
                else:  # Service cost allocation
                    # Get key-based cost share of default product
                    if default_cost_by_product_meter.total_keys != 0.0:
                        cost = default_cost_by_product_meter.adjusted_cost * self.provider_cost_allocation_key / \
                               default_cost_by_product_meter.total_keys
                    else:
                        cost = default_cost_by_product_meter.adjusted_cost / default_cost_by_product_meter.nb_keys

                    # Get key-based cost share of own product if any
                    if self.product:
                        cost_by_product_meter = \
                            provider_tag_selector.get_or_add_cost_by_product_meter(self.product,
                                                                                   self.product_meter_name)
                        if cost_by_product_meter.total_keys != 0.0:
                            cost += cost_by_product_meter.adjusted_cost * self.provider_cost_allocation_key / \
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

    def visit_for_cycles(self,
                         visited_service_instance_list: list['ServiceInstance'],
                         service_precedence_list: list[str]) -> None:
        # Recursively visit provider service instance
        if not self.is_self_consumption():  # Ignore self consumption
            self.provider_service_instance.visit_for_cycles(visited_service_instance_list, service_precedence_list)


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
        'selector',                # type: str
        'raw_cost',                # type: float
        'adjusted_cost',           # type: float
        'costs_by_product_meter',  # type: dict[ProviderTagSelectorCostByProductMeter]
    )

    def __init__(self, selector):
        self.selector = selector
        self.raw_cost = 0.0
        self.adjusted_cost = 0.0
        self.costs_by_product_meter = {}

    def get_or_add_cost_by_product_meter(self,
                                         product: str,
                                         product_meter_name: str) -> ProviderTagSelectorCostByProductMeter:
        product_meter_id = \
            ProviderTagSelectorCostByProductMeter.get_product_meter_id(product, product_meter_name)
        if product_meter_id not in self.costs_by_product_meter:
            self.costs_by_product_meter[product_meter_id] = ProviderTagSelectorCostByProductMeter(product,
                                                                                                  product_meter_name)
        return self.costs_by_product_meter[product_meter_id]

    def get_or_add_default_cost_by_product_meter(self) -> ProviderTagSelectorCostByProductMeter:
        return self.get_or_add_cost_by_product_meter('', '')

    def has_cost_by_product_meter(self, product: str, product_meter_name: str) -> bool:
        product_meter_id = \
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
    Represents the instance of a service and its costs
    """

    __slots__ = (

        # Identifiers
        'service',   # type: str
        'instance',  # type: str

        # Lists of items and consumer items
        'cost_items',           # type: list[CostItem]
        'consumer_cost_items',  # type: list[ConsumerCostItem]

        # Cost and flags for the visit algorithms
        'cost',              # type: float
        'is_visited',        # type: bool
        'is_being_visited',  # type: bool

        # The dictionary from provider tag selectors to their costs for this service instance
        'provider_tag_selector_cost_dict',  # type: dict[str,ProviderTagSelectorCost]
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
        if not self.is_provider():
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
                cost_by_product_meter = \
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
                    if not item.is_self_consumption():

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
                if item.nb_matching_provider_tag_selectors == 0 and not item.is_self_consumption():
                    item.nb_matching_provider_tag_selectors = 1
                    default_provider_tag_selector.raw_cost += item.cost
                    total_provider_tag_selector_raw_cost += item.cost
                    default_provider_tag_selector.update_costs_by_product_meter_raw_cost(item)

        # Check if provider tag selectors form a partition
        is_partition = True
        for item in self.cost_items:
            if not item.is_self_consumption() and item.nb_matching_provider_tag_selectors != 1:
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
                provider_tag_selector_cost.adjusted_cost = \
                    self.cost * provider_tag_selector_cost.raw_cost / total_provider_tag_selector_raw_cost

            else:
                # Adjust equally
                provider_tag_selector_cost.adjusted_cost = self.cost / len(self.provider_tag_selector_cost_dict)

            # Adjust costs by product meter
            for cost_by_product_meter in provider_tag_selector_cost.costs_by_product_meter.values():
                if provider_tag_selector_cost.raw_cost != 0.0:
                    # Adjust proportionally
                    cost_by_product_meter.adjusted_cost = cost_by_product_meter.raw_cost * \
                                                          provider_tag_selector_cost.adjusted_cost / \
                                                          provider_tag_selector_cost.raw_cost
                else:
                    # Adjust equally
                    cost_by_product_meter.adjusted_cost = provider_tag_selector_cost.adjusted_cost / \
                                                          len(provider_tag_selector_cost.costs_by_product_meter)

    @staticmethod
    def get_id(service: str, instance: str) -> str:
        return service + '.' + instance

    def get_self_id(self) -> str:
        return ServiceInstance.get_id(self.service, self.instance)

    def is_provider(self) -> bool:
        return bool(self.consumer_cost_items)

    def reset_visit(self) -> None:
        self.is_visited = False
        self.is_being_visited = False

    def reset_visit_for_allocation(self, is_for_products: bool) -> None:
        self.reset_visit()
        self.cost = 0.0
        for item in self.cost_items:
            item.reset_cost()
            if is_for_products:
                item.reset_product_cost()

    def visit_for_allocation(self,
                             visited_service_instance_list: list['ServiceInstance'],
                             ignore_cost_as_key: bool,
                             is_amortized_cost: bool,
                             is_for_products: bool) -> None:

        # Already visited?
        if self.is_visited:
            return

        # Cyclic cost allocation?
        if self.is_being_visited:
            message = StringIO()
            message.write("Found unexpected cost allocation cycle: ")
            for visited_service_instance in visited_service_instance_list:
                message.write(visited_service_instance.get_self_id() + ",")
            message.write(self.get_self_id())
            error(message.getvalue())
            raise CycleException

        # Visit items, except self-consumption, and update cost
        for item in self.cost_items:
            item.visit_for_allocation(visited_service_instance_list,
                                      ignore_cost_as_key,
                                      False,
                                      is_amortized_cost,
                                      is_for_products)
            self.cost += item.cost

        # Compute provider tag selector costs
        self.compute_provider_tag_selector_costs()

        # Visit self-consumption
        for item in self.cost_items:
            item.visit_for_allocation(visited_service_instance_list,
                                      ignore_cost_as_key,
                                      True,
                                      is_amortized_cost,
                                      is_for_products)

        # Set visited
        self.is_visited = True

    def visit_for_cycles(self,
                         visited_service_instance_list: list['ServiceInstance'],
                         service_precedence_list: list[str]) -> None:

        # Already visited?
        if self.is_visited:
            return

        # Cyclic cost allocation?
        if self.is_being_visited:

            # Create cycle message
            cycle_message = StringIO()
            for visited_service_instance in visited_service_instance_list:
                cycle_message.write(visited_service_instance.get_self_id() + ",")
            cycle_message.write(self.get_self_id())

            # Search for the first and the second service instances
            first_service_instance = None
            second_service_instance = None
            for service in service_precedence_list:
                for service_instance in visited_service_instance_list:
                    if service_instance.service == service:
                        if not first_service_instance:
                            first_service_instance = service_instance
                            break
                        elif not second_service_instance:
                            second_service_instance = service_instance
                            break
                if second_service_instance:
                    break

            # If two services in the precedence list do not exist in the cycle, the cycle cannot be broken
            if not second_service_instance:
                error("Unbreakable cost allocation cycle detected: " + cycle_message.getvalue())
                raise UnbreakableCycleException

            # Break the cycle before the first service instance
            for cost_item in first_service_instance.cost_items:
                provider_service_instance = cost_item.get_consumer_cost_item_provider_service_instance()
                if provider_service_instance and\
                   not provider_service_instance.is_visited and provider_service_instance.is_being_visited:
                    cost_item.is_removed_from_cycle = True
                    info("Broke cost allocation cycle at provider service instance " +
                         provider_service_instance.get_self_id() + ", as service instances " +
                         first_service_instance.get_self_id() + " and " + second_service_instance.get_self_id() +
                         " have been identified in the precedence list and in the cycle " + cycle_message.getvalue())

                    # Iterate to the next cycle break
                    raise BreakableCycleException

            # This code should be unreachable, but just in case
            error("Unbreakable cost allocation cycle detected, although service instances in the precedence list " +
                  first_service_instance.get_self_id() + " and " + second_service_instance.get_self_id() +
                  " have been identified in the cycle:" + cycle_message.getvalue())
            raise UnbreakableCycleException

        # Set being visited
        self.is_being_visited = True
        visited_service_instance_list.append(self)

        # Visit items
        for item in self.cost_items:
            item.visit_for_cycles(visited_service_instance_list, service_precedence_list)

        # Set visited
        self.is_visited = True

class CostItemFactory(object):
    """"
    Creates Cost Items
    """
    def create_cloud_cost_item(self) -> CloudCostItem:
        return CloudCostItem()

    def create_consumer_cost_item(self) -> ConsumerCostItem:
        return ConsumerCostItem()
#        return ConsumerCostItem(self.nb_provider_meters)

    def create_service_instance(self, service: str, instance: str) -> ServiceInstance:
        return ServiceInstance(service, instance)

# coding: utf-8

from abc import ABC, abstractmethod
from io import StringIO
from logging import debug, info, error
import re
import sys

from cloud_cost_allocation.exceptions import CycleException, BreakableCycleException, UnbreakableCycleException
from cloud_cost_allocation.config import Config


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
        'amounts',         # type: list[float]
                           # - 0 is amortized cost
                           # - 1 is on-demand cost
                           # - Next are further amounts
        'currency',        # type: str

        # Helpers
        'nb_matching_provider_tag_selectors',  # type: int
    )

    def __init__(self):
        self.date_str = ""
        self.service = ""
        self.instance = ""
        self.dimensions = {}
        self.tags = {}
        self.amounts = None
        self.currency = ""
        self.nb_matching_provider_tag_selectors = 0

    def get_consumer_cost_item_provider_service_instance(self) -> 'ServiceInstance':
        # Default behavior, overridden in child classes
        return None

    def get_product(self) -> str:
        # Default behavior, overridden in child classes
        return ''

    def get_product_amount(self, index: int) -> float:
        # Default behavior, overridden in child classes
        return 0.0

    def get_product_dimensions(self) -> list[dict[str, str]]:
        # Default behavior, overridden in child classes
        return []

    def get_product_meters(self) -> list[dict[str, str]]:
        # Default behavior, overridden in child classes
        return []

    def get_unallocated_product_amount(self, index: int) -> float:
        # Default behavior, overridden in child classes
        return 0.0

    def initialize(self, config: Config) -> None:
        self.amounts = [0.0] * config.nb_amounts

    def is_consumer_cost_item_removed_for_cycle(self) -> bool:
        # Default behavior, overridden in child classes
        return False

    def is_self_consumption(self) -> bool:
        # Default behavior, overridden in child classes
        return False

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
                             amount_to_allocation_key_indexes: dict[int]) -> None:
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

    def __init__(self):
        super().__init__()

    def get_unallocated_product_amount(self, index: int) -> float:
        return self.amounts[index]

    def visit_for_allocation(self,
                             visited_service_instance_list: list['ServiceInstance'],
                             ignore_cost_as_key: bool,
                             process_self_consumption: bool,
                             amount_to_allocation_key_indexes: dict[int]) -> None:
        # Nothing to do
        return

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
        'allocation_keys',                              # type: list[float]
                                                        # - 0 is cost allocation key
                                                        # - Next are further allocation keys
        'provider_cost_allocation_cloud_tag_selector',  # type: str
        'provider_meters',                              # type: list[dict[str,str]]
        'product',                                      # type: str
        'product_dimensions',                           # type: list[dict[str,str]]
        'product_meters',                               # type: list[dict[str,str]]
        'product_amounts',                              # type: list[float]
        'unallocated_product_amounts',                  # type: list[float]
                                                        # - 0 is product amortized cost
                                                        # - 1 is product on-demand cost
                                                        # - Next are further amounts

        # Helpers
        'is_removed_from_cycle',      # type: bool
        'provider_service_instance',  # type: ServiceInstance
    )

    def __init__(self,):
        super().__init__()
        self.provider_service = ""
        self.provider_instance = ""
        self.provider_tag_selector = ""
        self.provider_cost_allocation_type = ""
        self.allocation_keys = None
        self.provider_cost_allocation_cloud_tag_selector = ""
        self.provider_meters = None
        self.product = ""
        self.product_dimensions = None
        self.product_meters = None
        self.product_amounts = None
        self.unallocated_product_amounts = None
        self.is_removed_from_cycle = False
        self.provider_service_instance = None

    def get_consumer_cost_item_provider_service_instance(self) -> 'ServiceInstance':
        return self.provider_service_instance

    def get_product(self) -> str:
        return self.product

    def get_product_amount(self, index: int) -> float:
        return self.product_amounts[index]

    def get_product_dimensions(self) -> list[dict[str, str]]:
        return self.product_dimensions

    def get_product_meters(self) -> list[dict[str, str]]:
        return self.product_meters

    def get_unallocated_product_amount(self, index: int) -> float:
        return self.unallocated_product_amounts[index]

    def initialize(self, config: Config) -> None:
        super().initialize(config)
        self.allocation_keys = [0.0] * config.nb_allocation_keys
        self.provider_meters = [{}] * config.nb_provider_meters
        self.product_dimensions = [{}] * config.nb_product_dimensions
        self.product_meters = [{}] * config.nb_product_meters
        self.product_amounts = [0.0] * config.nb_amounts
        self.unallocated_product_amounts = [0.0] * config.nb_amounts

    def is_consumer_cost_item_removed_for_cycle(self) -> bool:
        return self.is_removed_from_cycle

    def is_self_consumption(self) -> bool:
        return True if self.service == self.provider_service and self.instance == self.provider_instance else False

    def set_cost_as_key(self, cost: float) -> None:
        if self.provider_cost_allocation_type == "Cost":
            self.allocation_keys[0] = cost

    def set_instance_links(self, cloud_cost_allocator: 'CloudCostAllocator') -> None:
        super().set_instance_links(cloud_cost_allocator)
        self.provider_service_instance = cloud_cost_allocator.get_service_instance(self.provider_service,
                                                                                   self.provider_instance)
        self.provider_service_instance.consumer_cost_items.append(self)

    def visit_for_allocation(self,
                             visited_service_instance_list: list['ServiceInstance'],
                             ignore_cost_as_key: bool,
                             process_self_consumption: bool,
                             amount_to_allocation_key_indexes: dict[int]) -> None:

        # Check self consumption
        if self.is_self_consumption() == process_self_consumption:

            # Recursively visit provider service instance
            if not self.is_self_consumption():
                self.provider_service_instance.visit_for_allocation(visited_service_instance_list,
                                                                    ignore_cost_as_key,
                                                                    amount_to_allocation_key_indexes)

            # Ignore cost as keys
            if not (ignore_cost_as_key and self.provider_cost_allocation_type == "Cost"):

                # Get provider amounts by product info for this cost item
                provider_tag_selector_amounts = \
                    self.provider_service_instance.provider_tag_selector_amounts[self.provider_tag_selector]
                provider_amounts_by_product_info = \
                    provider_tag_selector_amounts.get_or_add_amounts_by_product_info(self.product,
                                                                                     self.product_dimensions,
                                                                                     self.product_meters,
                                                                                     len(amount_to_allocation_key_indexes))

                # Process amounts
                index = 0
                for amount_index in sorted(amount_to_allocation_key_indexes.keys()):

                    # Compute amount and product amount
                    provider_amount = provider_amounts_by_product_info.adjusted_amounts[index]
                    provider_product_amount = provider_amounts_by_product_info.adjusted_product_amounts[index]
                    total_keys = provider_amounts_by_product_info.total_keys[index]
                    if total_keys != 0.0:
                        allocation_key_index = amount_to_allocation_key_indexes[amount_index]
                        ratio = self.allocation_keys[allocation_key_index] / total_keys
                        amount = provider_amount * ratio
                        product_amount = provider_product_amount * ratio
                    else:
                        nb_keys = provider_amounts_by_product_info.nb_keys[index]
                        amount = provider_amount / nb_keys
                        product_amount = provider_product_amount / nb_keys

                    # Update amounts
                    self.amounts[amount_index] = amount
                    if self.product:
                        self.product_amounts[amount_index] = product_amount
                    else:
                        self.unallocated_product_amounts[amount_index] = product_amount

                    # Next amount
                    index += 1

    def visit_for_cycles(self,
                         visited_service_instance_list: list['ServiceInstance'],
                         service_precedence_list: list[str]) -> None:
        # Recursively visit provider service instance
        if not self.is_self_consumption():  # Ignore self consumption
            self.provider_service_instance.visit_for_cycles(visited_service_instance_list, service_precedence_list)


class ProviderTagSelectorAmountsByProductInfo(object):
    """
    Represents the amounts allocated for a given provider tag selector for a given product
    """

    __slots__ = (
        'product',                   # type: str
        'product_dimensions',        # type: list[dict[str, str]]
        'product_meters',            # type: list[dict[str, str]]
        'raw_amounts',               # type: list[float]
        'raw_product_amounts',       # type: list[float]
        'adjusted_amounts',          # type: list[float]
        'adjusted_product_amounts',  # type: list[float]
        'total_keys',                # type: list[float]
        'nb_keys'                    # type: list[int]
    )

    def __init__(self,
                 product: str,
                 product_dimensions: list[dict[str, str]],
                 product_meters,
                 nb_amounts: int):
        self.product = product
        self.product_dimensions = product_dimensions
        self.product_meters = product_meters
        self.raw_amounts = [0.0] * nb_amounts
        self.raw_product_amounts = [0.0] * nb_amounts
        self.adjusted_amounts = [0.0] * nb_amounts
        self.adjusted_product_amounts = [0.0] * nb_amounts
        self.total_keys = [0.0] * nb_amounts
        self.nb_keys = [0] * nb_amounts

    @staticmethod
    def get_product_info_id(product: str,
                            product_dimensions: list[dict[str, str]],
                            product_meters: list[dict[str, str]]) -> str:
        product_meter_id = product
        for product_dimension in product_dimensions:
            product_meter_id += "."
            if "Name" in product_dimension:
                product_meter_id += product_dimension["Name"]
            product_meter_id += "="
            if "Element" in product_dimension:
                product_meter_id += product_dimension["Element"]
        for product_meter in product_meters:
            product_meter_id += "."
            if "Name" in product_meter:
                product_meter_id += product_meter["Name"]
        return product_meter_id

    def get_affinity_score(self,
                           provider_product: str,
                           provider_product_dimensions: list[dict[str, str]],
                           provider_product_meters: list[dict[str, str]]) -> int:
        
        # Default score
        score = 0

        # Check same product or no product for both consumer and provider
        if self.product == provider_product:
            score = 1

            # Increase score if product dimensions and product meters match
            if self.product:
                
                # Check product dimension
                product_dimension_index = 0
                for product_dimension in self.product_dimensions:
                    provider_product_dimension = provider_product_dimensions[product_dimension_index]
                    if len(product_dimension) != 0 and len(provider_product_dimension) != 0:
                        if product_dimension['Name'] == provider_product_dimension['Name']:
                            score += 1
                        else:
                            break
                        if product_dimension['Element'] == provider_product_dimension['Element']:
                            score += 1
                        else:
                            break
                    else:
                        break
                    product_dimension_index += 1

                # Check product meters
                product_meter_index = 0
                for product_meter in self.product_meters:
                    provider_product_meter = provider_product_meters[product_meter_index]
                    if len(product_meter) != 0 and len(provider_product_meter) != 0:
                        if product_meter['Name'] == provider_product_meter['Name']:
                            score += 1
                        else:
                            break
                    else:
                        break
                    product_meter_index += 1

        # Provider costs with no product are equally allocated to consumers with products and with no product
        elif self.product and not provider_product:
            score = 1

        return score

    def is_default(self) -> bool:
        return True if len(self.product) == 0 else False


class ProviderTagSelectorAmounts(object):
    """
    Represents the amounts allocated for a given provider tag selector
    """

    __slots__ = (
        'selector',                   # type: str
        'raw_amounts',                # type: list[float]
        'raw_product_amounts',        # type: list[float]
        'adjusted_amounts',           # type: list[float]
        'adjusted_product_amounts',   # type: list[float]
        'amounts_by_product_info',    # type: dict[ProviderTagSelectorAmountsByProductInfo]
    )

    def __init__(self, selector: str, nb_amounts: int):
        self.selector = selector
        self.raw_amounts = [0.0] * nb_amounts
        self.raw_product_amounts = [0.0] * nb_amounts
        self.adjusted_amounts = [0.0] * nb_amounts
        self.adjusted_product_amounts = [0.0] * nb_amounts
        self.amounts_by_product_info = {}

    def get_or_add_amounts_by_product_info(self,
                                           product: str,
                                           product_dimensions: list[dict[str, str]],
                                           product_meters: list[dict[str, str]],
                                           nb_amounts: int)\
            -> ProviderTagSelectorAmountsByProductInfo:
        product_info_id = \
            ProviderTagSelectorAmountsByProductInfo.get_product_info_id(product, product_dimensions, product_meters)
        if product_info_id not in self.amounts_by_product_info:
            self.amounts_by_product_info[product_info_id] = ProviderTagSelectorAmountsByProductInfo(product,
                                                                                                    product_dimensions,
                                                                                                    product_meters,
                                                                                                    nb_amounts)
        return self.amounts_by_product_info[product_info_id]

    def is_default(self) -> bool:
        return True if len(self.selector) == 0 else False

    def update_raw_amounts(self,
                           provider_cost_item: CostItem,
                           total_raw_amounts: list[float],
                           total_raw_product_amounts: list[float],
                           amount_to_allocation_key_indexes: dict[int]) -> None:

        # Find most similar cost by product meters
        provider_product = provider_cost_item.get_product()
        provider_product_dimensions = provider_cost_item.get_product_dimensions()
        provider_product_meters = provider_cost_item.get_product_meters()
        most_similar_amounts_by_product_info = []
        highest_similarity_score = 0
        for amounts_by_product_info in self.amounts_by_product_info.values():
            similarity_score = amounts_by_product_info.get_affinity_score(provider_product,
                                                                          provider_product_dimensions,
                                                                          provider_product_meters)
            if similarity_score > highest_similarity_score:
                most_similar_amounts_by_product_info = [amounts_by_product_info]
                highest_similarity_score = similarity_score
            elif similarity_score == highest_similarity_score:
                most_similar_amounts_by_product_info.append(amounts_by_product_info)

        # No most similar exist, then it's all
        if not most_similar_amounts_by_product_info:
            most_similar_amounts_by_product_info = self.amounts_by_product_info.values()
        nb_most_similar_amounts_by_product_info = len(most_similar_amounts_by_product_info)

        # Process amounts
        index = 0
        for amount_index in sorted(amount_to_allocation_key_indexes.keys()):

            # Update raw amounts
            raw_amount = provider_cost_item.amounts[amount_index]
            self.raw_amounts[index] += raw_amount
            total_raw_amounts[index] += raw_amount
            raw_product_amount = provider_cost_item.get_unallocated_product_amount(amount_index)
            self.raw_product_amounts[index] += raw_product_amount
            total_raw_product_amounts[index] += raw_product_amount

            # Distribute raw amount across most similar amounts by product infos proportionally to their total keys
            total_keys = 0.0
            for amounts_by_product_info in most_similar_amounts_by_product_info:
                total_keys += amounts_by_product_info.total_keys[index]
            for amounts_by_product_info in most_similar_amounts_by_product_info:
                if total_keys != 0.0:
                    ratio = amounts_by_product_info.total_keys[index] / total_keys
                    amounts_by_product_info.raw_amounts[index] += raw_amount * ratio
                    amounts_by_product_info.raw_product_amounts[index] += raw_product_amount * ratio
                else:
                    amounts_by_product_info.raw_amounts[index] +=\
                        raw_amount / nb_most_similar_amounts_by_product_info
                    amounts_by_product_info.raw_product_amounts[index] +=\
                        raw_product_amount / nb_most_similar_amounts_by_product_info

            # Next amount
            index += 1


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

        # Flags for the visit algorithms
        'is_visited',        # type: bool
        'is_being_visited',  # type: bool

        # The dictionary from provider tag selectors to their costs for this service instance
        'provider_tag_selector_amounts',  # type: dict[str,ProviderTagSelectorAmounts]
    )

    def __init__(self, service: str, instance: str):
        self.service = service
        self.instance = instance
        self.cost_items = []
        self.consumer_cost_items = []
        self.is_visited = False
        self.is_being_visited = False
        self.provider_tag_selector_amounts = {}

    def compute_provider_tag_selector_amounts(self, amount_to_allocation_key_indexes: dict[int]) -> None:

        # Nothing to do if not provider
        if not self.is_provider():
            return

        # Compute the amounts and the product amounts to allocate for this service instance as provider
        service_instance_amounts = []
        service_instance_product_amounts = []
        for amount_index in sorted(amount_to_allocation_key_indexes.keys()):
            service_instance_amount = 0.0
            service_instance_product_amount = 0.0
            for cost_item in self.cost_items:
                if not cost_item.is_self_consumption():
                    service_instance_amount += cost_item.amounts[amount_index]
                    service_instance_product_amount += cost_item.get_unallocated_product_amount(amount_index)
            service_instance_amounts.append(service_instance_amount)
            service_instance_product_amounts.append(service_instance_product_amount)

        # Initiate provider tag selector amounts and amounts by product info, by processing consumer items
        self.provider_tag_selector_amounts = {}
        nb_amounts = len(amount_to_allocation_key_indexes)
        for consumer_item in self.consumer_cost_items:

            # Create provider tag selector, if it does not exist yet
            if consumer_item.provider_tag_selector not in self.provider_tag_selector_amounts:
                self.provider_tag_selector_amounts[consumer_item.provider_tag_selector] = \
                    ProviderTagSelectorAmounts(consumer_item.provider_tag_selector, nb_amounts)
            provider_tag_selector_amount = self.provider_tag_selector_amounts[consumer_item.provider_tag_selector]

            # Get or add cost by product meters, and update keys
            amounts_by_product_info = \
                provider_tag_selector_amount.get_or_add_amounts_by_product_info(consumer_item.product,
                                                                                consumer_item.product_dimensions,
                                                                                consumer_item.product_meters,
                                                                                nb_amounts)
            index = 0
            for amount_index in sorted(amount_to_allocation_key_indexes.keys()):
                allocation_key_index = amount_to_allocation_key_indexes[amount_index]
                amounts_by_product_info.total_keys[index] += consumer_item.allocation_keys[allocation_key_index]
                amounts_by_product_info.nb_keys[index] += 1
                index += 1

        # We will check whether provider tag selectors form a mathematical partition of the provider
        # cost items, i.e. if every provider cost item is matched by a single provider tag selector
        # We will also compute for every provider tag selector the (raw) amounts of the provider cost items
        # that are matched by the provider tag selector
        # If the provider tag selectors do not form a partition, the selected (raw) amounts of provider tag
        # selectors will be adjusted proportionally so that the sum equals the sum of provider cost items

        # Process the simple common case of a single provider tag selector
        is_partition = True
        total_provider_tag_selector_raw_amounts = [0.0] * nb_amounts
        total_provider_tag_selector_raw_product_amounts = [0.0] * nb_amounts
        if len(self.provider_tag_selector_amounts) == 1:

            # For debug
            provider_tag_selector_amount = list(self.provider_tag_selector_amounts.values())[0]
            if not provider_tag_selector_amount.is_default():
                debug("Provider service instance " + self.service + "." + self.instance +
                      " has a single provider tag selector, which is not empty")

            # Update raw amounts
            for cost_item in self.cost_items:
                if not cost_item.is_self_consumption():
                    provider_tag_selector_amount\
                        .update_raw_amounts(cost_item,
                                            total_provider_tag_selector_raw_amounts,
                                            total_provider_tag_selector_raw_product_amounts,
                                            amount_to_allocation_key_indexes)

        else:  # Case of multiple provider tag selectors

            # Reset the number of matching provider tag selectors of every cost item, and build tag dict:
            # - Key is cost item is tag string
            # - Value is list of cost items
            # Since multiple cost items may have the same tags, the goal is to minimize the number of tag evaluations
            cost_item_tag_dict = {}
            for cost_item in self.cost_items:
                if not cost_item.is_self_consumption():
                    cost_item.nb_matching_provider_tag_selectors = 0
                    tag_string = str(cost_item.tags)
                    if tag_string in cost_item_tag_dict:
                        cost_item_list = cost_item_tag_dict[tag_string]
                    else:
                        cost_item_list = []
                        cost_item_tag_dict[tag_string] = cost_item_list
                    cost_item_list.append(cost_item)

            # Build evaluation error dict, used to avoid error streaming in case of incorrect provider tag
            # selector expression
            # Key = date, provider service, provider instance, provider tag selector, expression
            # Value = count of errors
            evaluation_error_dict = {}

            # Compute raw costs of non-default provider tag selectors, by checking matching items
            for cost_item_tag, cost_item_list in cost_item_tag_dict.items():
                for provider_tag_selector_amount in self.provider_tag_selector_amounts.values():
                    if not provider_tag_selector_amount.is_default():

                        # Check if item matches provider tag selector
                        eval_globals_dict = {}
                        for key, value in cost_item_list[0].tags.items():
                            eval_globals_dict[re.sub(r'[^a-z0-9_]', '_', key)] = value
                        eval_true = False
                        try:
                            # Eval is dangerous. Considerations:
                            # - Audit cost allocation keys, which are provided by DevOps
                            # - Possibly forbid provider tag selectors
                            eval_true = eval(provider_tag_selector_amount.selector, eval_globals_dict, {})
                        except:
                            exception = sys.exc_info()[0]
                            error_key =\
                                cost_item_list[0].date_str + chr(10) + self.service + chr(10) + self.instance + chr(10) +\
                                provider_tag_selector_amount.selector + chr(10) + str(exception)
                            if error_key in evaluation_error_dict:
                                error_count = evaluation_error_dict[error_key]
                            else:
                                error_count = 0
                            evaluation_error_dict[error_key] = error_count + 1

                        # If item matches provider tag selector, update raw amounts of the provider tag selector
                        if eval_true:
                            for cost_item in cost_item_list:
                                cost_item.nb_matching_provider_tag_selectors += 1
                                provider_tag_selector_amount\
                                    .update_raw_amounts(cost_item,
                                                        total_provider_tag_selector_raw_amounts,
                                                        total_provider_tag_selector_raw_product_amounts,
                                                        amount_to_allocation_key_indexes)

            # Log evaluation errors
            for error_key, error_count in evaluation_error_dict.items():
                error_fields = error_key.split(chr(10))
                date_str = error_fields[0]
                provider_service = error_fields[1]
                provider_instance = error_fields[2]
                provider_tag_selector = error_fields[3]
                exception = error_fields[4]
                error("Caught exception '" + exception + "' " + str(error_count) + " times " +
                      "when evaluating ProviderTagSelector '" + provider_tag_selector +
                      "' of ProviderService '" + provider_service +
                      "' and of ProviderInstance '" + provider_instance + "'" +
                      ", for date " + date_str)

            # Compute the raw amounts of the default provider tag selector
            if '' in self.provider_tag_selector_amounts:
                default_provider_tag_selector = self.provider_tag_selector_amounts['']
                for cost_item in self.cost_items:
                    if cost_item.nb_matching_provider_tag_selectors == 0 and not cost_item.is_self_consumption():
                        cost_item.nb_matching_provider_tag_selectors = 1
                        default_provider_tag_selector.update_raw_amounts(cost_item,
                                                                         total_provider_tag_selector_raw_amounts,
                                                                         total_provider_tag_selector_raw_product_amounts,
                                                                         amount_to_allocation_key_indexes)

            # Check if provider tag selectors form a partition
            for item in self.cost_items:
                if not item.is_self_consumption() and item.nb_matching_provider_tag_selectors != 1:
                    is_partition = False

        # For debug
        if not is_partition:
            debug("Provider tag selectors of provider service instance " + self.service + "." + self.instance +
                  " do not form a partition")

        # Adjust amounts
        for index in range(nb_amounts):
            for provider_tag_selector_amount in self.provider_tag_selector_amounts.values():

                # Adjust provider tag selector amounts
                if is_partition:  # I love it when a plan comes together
                    provider_tag_selector_amount.adjusted_amounts[index] =\
                        provider_tag_selector_amount.raw_amounts[index]
                    provider_tag_selector_amount.adjusted_product_amounts[index] =\
                        provider_tag_selector_amount.raw_product_amounts[index]

                else:  # Provider tag selectors overlap and/or are incomplete

                    # Adjust amount
                    if total_provider_tag_selector_raw_amounts[index] != 0.0:
                        # Some cost items are matched by provider tag selectors
                        # Adjust proportionally
                        provider_tag_selector_amount.adjusted_amounts[index] =\
                            service_instance_amounts[index] * provider_tag_selector_amount.raw_amounts[index] /\
                            total_provider_tag_selector_raw_amounts[index]
                    else:  # No selector matches any item!
                        # Adjust equally
                        provider_tag_selector_amount.adjusted_amounts[index] =\
                            service_instance_amounts[index] / len(self.provider_tag_selector_amounts)

                    # Adjust product amount
                    if total_provider_tag_selector_raw_product_amounts[index] != 0.0:
                        # Some cost items are matched by provider tag selectors
                        # Adjust proportionally
                        provider_tag_selector_amount.adjusted_product_amounts[index] =\
                            service_instance_product_amounts[index] *\
                            provider_tag_selector_amount.raw_product_amounts[index] /\
                            total_provider_tag_selector_raw_amounts[index]
                    else:  # No selector matches any item!
                        # Adjust equally
                        provider_tag_selector_amount.adjusted_product_amounts[index] =\
                            service_instance_product_amounts[index] / len(self.provider_tag_selector_amounts)

                # Adjust amounts by product info
                for amounts_by_product_info in provider_tag_selector_amount.amounts_by_product_info.values():

                    # Adjust amount
                    if provider_tag_selector_amount.raw_amounts[index] != 0.0:
                        # Adjust proportionally
                        amounts_by_product_info.adjusted_amounts[index] =\
                            provider_tag_selector_amount.adjusted_amounts[index] *\
                            amounts_by_product_info.raw_amounts[index] /\
                            provider_tag_selector_amount.raw_amounts[index]
                    else:
                        # Adjust equally
                        amounts_by_product_info.adjusted_amounts[index] =\
                            provider_tag_selector_amount.adjusted_amounts[index] / \
                            len(provider_tag_selector_amount.amounts_by_product_info)

                    # Adjust product amount
                    if provider_tag_selector_amount.raw_product_amounts[index] != 0.0:
                        # Adjust proportionally
                        amounts_by_product_info.adjusted_product_amounts[index] =\
                            provider_tag_selector_amount.adjusted_product_amounts[index] *\
                            amounts_by_product_info.raw_product_amounts[index] /\
                            provider_tag_selector_amount.raw_product_amounts[index]
                    else:
                        # Adjust equally
                        amounts_by_product_info.adjusted_product_amounts[index] =\
                            provider_tag_selector_amount.adjusted_product_amounts[index] / \
                            len(provider_tag_selector_amount.amounts_by_product_info)

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

    def visit_for_allocation(self,
                             visited_service_instance_list: list['ServiceInstance'],
                             ignore_cost_as_key: bool,
                             amount_to_allocation_key_indexes: dict[int]) -> None:

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

        # Visit items, except self-consumption
        for cost_item in self.cost_items:
            cost_item.visit_for_allocation(visited_service_instance_list,
                                           ignore_cost_as_key,
                                           False,
                                           amount_to_allocation_key_indexes)

        # Compute provider tag selector amounts
        self.compute_provider_tag_selector_amounts(amount_to_allocation_key_indexes)

        # Visit self-consumption
        for item in self.cost_items:
            item.visit_for_allocation(visited_service_instance_list,
                                      ignore_cost_as_key,
                                      True,
                                      amount_to_allocation_key_indexes)

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

            # Iterate in reducing service precedence list
            working_service_precedence_list = service_precedence_list.copy()
            while working_service_precedence_list:

                # Search for the first service and the second service
                first_service = None
                second_service = None
                for service in working_service_precedence_list:
                    for service_instance in visited_service_instance_list:
                        if service_instance.service == service:
                            if not first_service:
                                first_service = service
                                break
                            elif not second_service:
                                second_service = service
                                break
                    if second_service:
                        break

                # If two services in the precedence list do not exist in the cycle, the cycle cannot be broken
                if not second_service:
                    break

                # Try to break the cycle before the first service
                for service_instance in visited_service_instance_list:
                    if service_instance.service == first_service:
                        for cost_item in service_instance.cost_items:
                            provider_service_instance = cost_item.get_consumer_cost_item_provider_service_instance()
                            if provider_service_instance and\
                               not provider_service_instance.is_visited and provider_service_instance.is_being_visited:
                                cost_item.is_removed_from_cycle = True
                                info("Broke cost allocation cycle at provider service instance " +
                                     provider_service_instance.get_self_id() + " of service instance " +
                                     service_instance.get_self_id() + ", as services " +
                                     first_service + " and " + second_service +
                                     " have been identified in the precedence list and in the cycle " +
                                     cycle_message.getvalue())

                                # Iterate to the next cycle break
                                raise BreakableCycleException

                # Reduce service precedence list
                working_service_precedence_list.pop(0)

            # If this code is reached, it means cycle could not be broken
            error("Unbreakable cost allocation cycle detected: " + cycle_message.getvalue())
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

    __slots__ = (
        'config',                 # type: Config
        'dimensions',             # type: list[str]
        'nb_amounts',             # type: int
        'nb_allocation_keys',     # type: int
        'nb_provider_meters',     # type: int
        'nb_product_dimensions',  # type: int
        'nb_product_meters',      # type: int
    )

    def __init__(self, config: Config):

        # Config and factory
        self.config = config

    def create_cloud_cost_item(self) -> CloudCostItem:
        cloud_cost_item = CloudCostItem()
        cloud_cost_item.initialize(self.config)
        return cloud_cost_item

    def create_consumer_cost_item(self) -> ConsumerCostItem:
        consumer_cost_item = ConsumerCostItem()
        consumer_cost_item.initialize(self.config)
        return consumer_cost_item

    def create_service_instance(self, service: str, instance: str) -> ServiceInstance:
        return ServiceInstance(service, instance)

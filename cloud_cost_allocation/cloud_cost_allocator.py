# coding: utf-8

# Standard imports
from logging import info, error
import re
import sys

# Cloud cost allocation imports
from cloud_cost_allocation.cost_items import CloudCostItem, ConsumerCostItem, CostItemFactory, \
    CostItem, ServiceInstance
from cloud_cost_allocation.exceptions import CycleException, BreakableCycleException, UnbreakableCycleException
from cloud_cost_allocation.utils.utils import is_float


class CloudCostAllocator(object):
    """
    Allocates cloud costs
    """

    __slots__ = (
        'cost_item_factory',  # type: CostItemFactory
        'date_str',           # type: str
        'currency',           # type: str
        'service_instances',  # type: dict[ServiceInstance]
    )

    def __init__(self, cost_item_factory: CostItemFactory):
        self.cost_item_factory = cost_item_factory
        self.date_str = ""
        self.currency = ""
        self.service_instances = {}

    def allocate(self, consumer_cost_items: list[ConsumerCostItem],
                 cloud_cost_items: list[CloudCostItem],
                 amounts: list[str]) -> bool:

        # Get config
        config = self.cost_item_factory.config

        # Date and currency must be defined
        if not self.date_str:
            error("CloudCostAllocator.date_str must be set")
            return False
        if not self.currency:
            error("CloudCostAllocator.currency must be set, for date " + self.date_str)
            return False

        # Initiate cost items with cloud cost items
        cost_items = []
        cost_items.extend(cloud_cost_items)

        # Identify cloud tag selectors and default product consumer cost items
        # Also check if cost is used as cost allocation type
        cloud_tag_selector_consumer_cost_items = []
        default_product_consumer_cost_items = {}
        is_cost_used_as_cost_allocation_type = False
        for consumer_cost_item in consumer_cost_items:
            if consumer_cost_item.provider_cost_allocation_type == "CloudTagSelector":
                cloud_tag_selector_consumer_cost_items.append(consumer_cost_item)
            elif consumer_cost_item.provider_cost_allocation_type == "DefaultProduct":
                provider_service = consumer_cost_item.provider_service
                if provider_service in default_product_consumer_cost_items:
                    default_product_consumer_cost_items[provider_service].append(consumer_cost_item)
                else:
                    default_product_consumer_cost_items[provider_service] = [consumer_cost_item]
            else:
                if consumer_cost_item.provider_cost_allocation_type == "Cost":
                    is_cost_used_as_cost_allocation_type = True
                cost_items.append(consumer_cost_item)

        # Process cloud tag selectors
        info("Processing cloud tag selectors, for date " + self.date_str)
        self.process_cloud_tag_selectors(cost_items, cloud_tag_selector_consumer_cost_items, cloud_cost_items)

        # Create and add cloud consumer cost item from tags
        info("Creating consumer cost items from tags, for date " + self.date_str)
        new_consumer_cost_items = []
        self.create_consumer_cost_items_from_tags(new_consumer_cost_items, cost_items)
        cost_items.extend(new_consumer_cost_items)

        # Untangle cycles, using upstream list
        info("Untangling cycles, for date " + self.date_str)
        cost_items = self.untangle_cycles(cost_items)

        # Process default products
        cost_items = self.process_default_products(cost_items, default_product_consumer_cost_items)

        # Check dates
        cleansed_cost_items = []
        different_date_str_dict = {}
        for cost_item in cost_items:
            if cost_item.date_str == self.date_str:
                cleansed_cost_items.append(cost_item)
            else:
                if cost_item.date_str in different_date_str_dict:
                    different_date_str_dict[cost_item.date_str] = different_date_str_dict[cost_item.date_str] + 1
                else:
                    different_date_str_dict[cost_item.date_str] = 1
        for date_str, nb_cost_items in different_date_str_dict.items():
            error("Skipped " + str(nb_cost_items) +
                  " cost items having dates " + date_str +
                  " instead of " + self.date_str)
        cost_items = cleansed_cost_items

        # Check currencies
        cleansed_cost_items = []
        different_currency_dict = {}
        for cost_item in cost_items:
            if not cost_item.currency:
                cost_item.currency = self.currency
                cleansed_cost_items.append(cost_item)
            elif cost_item.currency == self.currency:
                cleansed_cost_items.append(cost_item)
            else:
                if cost_item.currency in different_currency_dict:
                    different_currency_dict[cost_item.currency] = different_currency_dict[cost_item.currency] + 1
                else:
                    different_currency_dict[cost_item.currency] = 1
        for currency, nb_cost_items in different_currency_dict.items():
            error("Skipped " + str(nb_cost_items) +
                  " cost items having currencies " + currency +
                  " instead of " + self.currency +
                  ", for date " + self.date_str)
        cost_items = cleansed_cost_items

        # Break cycles, using precedence list
        # When a cycle is broken, ConsumerCostItem.is_removed_from_cycle is set to True at the cycle break point
        info("Breaking cycles, for date " + self.date_str)
        if not self.break_cycles(cost_items):
            return False

        # Reset instances
        self.reset_instances(cost_items)

        # Protect against unexpected cycles
        try:

            # Build amount allocation key indexes dictionary
            amount_to_allocation_key_indexes = {}
            if not config.build_amount_to_allocation_key_indexes(amount_to_allocation_key_indexes, amounts):
                return False

            # Allocate costs, ignoring the keys that are using cost, and then
            # set these keys from the allocated cost
            if is_cost_used_as_cost_allocation_type:  # Save run time if not needed
                info("Allocating costs, ignoring keys that are costs, for date " + self.date_str)
                self.visit_for_allocation(True, False, amount_to_allocation_key_indexes)
                for service_instance in self.service_instances.values():
                    service_instance_cost = [0.0] * config.nb_amounts
                    for cost_item in service_instance.cost_items:
                        if not cost_item.is_self_consumption():
                            for i in range(config.nb_amounts):
                                service_instance_cost[i] += cost_item.amounts[i]
                    for cost_item in service_instance.cost_items:
                        cost_item.set_cost_as_key(service_instance_cost, config)

            # Allocate costs for services
            info("Allocating costs, for date " + self.date_str)
            self.visit_for_allocation(False, False, amount_to_allocation_key_indexes)

        except CycleException:
            return False

        return True

    def allocate_further_amounts(self, cost_items: list[CostItem], amounts: list[str]) -> bool:

        # Build amount allocation key indexes dictionary
        amount_to_allocation_key_indexes = {}
        if not self.cost_item_factory.config.build_amount_to_allocation_key_indexes(amount_to_allocation_key_indexes,
                                                                                    amounts):
            return False

        # Reset instances
        self.reset_instances(cost_items)

        # Visit, by protecting against unexpected cycles
        try:
            self.visit_for_allocation(False, True, amount_to_allocation_key_indexes)
        except CycleException:
            return False

        return True

    def break_cycles(self, cost_items: list[CostItem]) -> bool:

        # Build service precedence list
        config = self.cost_item_factory.config.config
        service_precedence_list = []
        if 'Cycles' in config and 'ServicePrecedenceList' in config['Cycles']:
            for service in config['Cycles']['ServicePrecedenceList'].replace("\n", "").split(","):
                service_precedence_list.append(service.strip().lower())

        # Get max cycle breaks
        max_breaks = 10  # Default value
        if 'Cycles' in config and 'MaxBreaks' in config['Cycles']:
            max_breaks = int(config['Cycles']['MaxBreaks'])

        # Break cycles
        nb_breaks = 0
        while nb_breaks < max_breaks:

            # Log
            info("Detecting and breaking cycles, for date " + self.date_str + ": pass " + str(nb_breaks))

            # Reset instances
            self.reset_instances(cost_items)

            # Reset visit
            for service_instance in self.service_instances.values():
                service_instance.reset_visit()

            # Visit cycles
            try:

                # Visit instances
                for service_instance in self.service_instances.values():
                    visited_service_instance_list = []
                    service_instance.visit_for_cycles(visited_service_instance_list, service_precedence_list)

                # No cycle was found
                break

            except BreakableCycleException:
                nb_breaks += 1

            except UnbreakableCycleException:
                return False

        # Return Ok if the number of max cycles breaks was not reached
        if nb_breaks < max_breaks:
            return True
        else:
            error("Max number of cost allocation cycle breaks was reached, for date " + self.date_str)
            return False

    def create_consumer_cost_items_from_tags(self,
                                             new_consumer_cost_items: list[ConsumerCostItem],
                                             cost_items: list[CostItem]) -> None:

        # If consumer tag or product tag is used, process cost items
        config = self.cost_item_factory.config
        if config.consumer_service_tag_keys or config.product_tag_keys:
            for cost_item in cost_items:

                # Check consumer service
                consumer_service = ""
                actual_consumer_service_tag_key = ""
                for consumer_service_tag_key in config.consumer_service_tag_keys:
                    if consumer_service_tag_key in cost_item.tags:
                        actual_consumer_service_tag_key = consumer_service_tag_key
                        consumer_service = cost_item.tags[consumer_service_tag_key].strip().lower()
                        break

                # Check if consumer service must be ignored
                for consumer_service_ignored_value in config.consumer_service_ignored_tag_values:
                    if consumer_service == consumer_service_ignored_value.strip().lower():
                        consumer_service = ""

                # Check consumer instance
                consumer_instance = ""
                actual_consumer_instance_tag_key = ""
                for consumer_instance_tag_key in config.consumer_instance_tag_keys:
                    if consumer_instance_tag_key in cost_item.tags:
                        actual_consumer_instance_tag_key = consumer_instance_tag_key
                        consumer_instance = cost_item.tags[consumer_instance_tag_key].strip().lower()
                        break

                # Check product
                # TODO: product dimension
                # TODO: product ignored value
                product = ""
                actual_product_tag_key = ""
                for product_tag_key in config.product_tag_keys:
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
                        actual_consumer_service_tag_variable = re.sub(r'[^a-z0-9_]',
                                                                      '_',
                                                                      actual_consumer_service_tag_key)
                        new_consumer_cost_item.provider_tag_selector = \
                            "'" + actual_consumer_service_tag_variable + "' in globals() and " + \
                            actual_consumer_service_tag_variable + "=='" + consumer_service + "'"
                        if actual_consumer_instance_tag_key:
                            actual_consumer_instance_tag_variable = re.sub(r'[^a-z0-9_]',
                                                                           '_',
                                                                           actual_consumer_instance_tag_key)
                            new_consumer_cost_item.provider_tag_selector += \
                                " and '" + actual_consumer_instance_tag_variable + "' in globals() and " + \
                                actual_consumer_instance_tag_variable + "=='" + consumer_instance + "'"
                    if actual_product_tag_key:
                        actual_product_tag_variable = re.sub(r'[^a-z0-9_]', '_', actual_product_tag_key)
                        if new_consumer_cost_item.provider_tag_selector:
                            new_consumer_cost_item.provider_tag_selector += " and "
                        new_consumer_cost_item.provider_tag_selector += \
                            "'" + actual_product_tag_variable + "' in globals() and " + \
                            actual_product_tag_variable + "=='" + product + "'"
                    new_consumer_cost_item.provider_cost_allocation_type = "ConsumerTag"
                    for i in range(config.nb_allocation_keys):
                        new_consumer_cost_item.allocation_keys[i] = 1.0
                    new_consumer_cost_item.product = product

                    # Add consumer dimensions
                    for dimension, consumer_dimension_tag_keys in config.consumer_dimension_tag_keys.items():
                        for consumer_dimension_tag_key in consumer_dimension_tag_keys:
                            if consumer_dimension_tag_key in cost_item.tags:
                                new_consumer_cost_item.dimensions[dimension] = \
                                    cost_item.tags[consumer_dimension_tag_key].strip().lower()
                                break

                    # Add cloud consumer cost item
                    new_consumer_cost_items.append(new_consumer_cost_item)

    def get_service_instance(self, service: str, instance: str) -> ServiceInstance:
        service_instance_id = ServiceInstance.get_id(service, instance)
        if service_instance_id not in self.service_instances:  # Create service instance if not existing yet
            service_instance = self.cost_item_factory.create_service_instance(service, instance)
            self.service_instances[service_instance_id] = service_instance
        return self.service_instances[service_instance_id]

    def process_cloud_tag_selectors(self,
                                    cost_items: list[CostItem],
                                    cloud_tag_selector_consumer_cost_items: list[ConsumerCostItem],
                                    cloud_cost_items: list[CloudCostItem]) -> None:

        # Get number of allocation keys
        nb_allocation_keys = self.cost_item_factory.config.nb_allocation_keys

        # Build evaluation error dict, used to avoid error streaming in case of incorrect cloud tag selector expression
        # Key = provider service, provider instance, cloud tag selector expression, exception
        # Value = count of errors
        evaluation_error_dict = {}

        # Build cloud tag dict: key is cloud cost item tag string; value is list of cloud cost items
        # Since a lot of cloud cost items have the same tags, the goal is to minimize the number of tag evaluation
        # contexts
        cloud_tag_dict = {}
        for cloud_cost_item in cloud_cost_items:
            tag_string = str(cloud_cost_item.tags)
            if tag_string in cloud_tag_dict:
                cloud_cost_item_list = cloud_tag_dict[tag_string]
            else:
                cloud_cost_item_list = []
                cloud_tag_dict[tag_string] = cloud_cost_item_list
            cloud_cost_item_list.append(cloud_cost_item)

        # Create a unique consumer cost item for a given consumer service instance and for a given cloud tag
        # selector consumer cost item
        # TODO: Create different consumer cost items for different consumer cost item dimensions
        new_consumer_cost_items = {}
        # Key is (consumer service instance id, number of cloud tag selector consumer in input list)

        # Process cloud tag dict
        for cloud_cost_item_list in cloud_tag_dict.values():

            # Build variables from tags
            eval_globals_dict = {}
            for key, value in cloud_cost_item_list[0].tags.items():
                eval_globals_dict[re.sub(r'[^a-z0-9_]', '_', key)] = value

            # Process consumer cost items
            selector_nb = 0
            for cloud_tag_selector_consumer_cost_item in cloud_tag_selector_consumer_cost_items:
                selector_nb += 1

                # Check if cloud selector match
                provider_service = cloud_tag_selector_consumer_cost_item.provider_service
                provider_instance = cloud_tag_selector_consumer_cost_item.provider_instance
                cloud_tag_selector = cloud_tag_selector_consumer_cost_item.provider_cost_allocation_cloud_tag_selector
                match = False
                try:
                    # Eval is dangerous. Considerations:
                    # - Possibly forbid cloud tag selectors
                    # - Possibly whitelist cloud tag selectors using pattern matching
                    match = eval(cloud_tag_selector, eval_globals_dict, {})
                except:
                    exception = sys.exc_info()[0]
                    error_key =\
                        provider_service + chr(10) +\
                        provider_instance + chr(10) +\
                        cloud_tag_selector + chr(10) +\
                        str(exception)
                    if error_key in evaluation_error_dict:
                        error_count = evaluation_error_dict[error_key]
                    else:
                        error_count = 0
                    evaluation_error_dict[error_key] = error_count + 1
                if match:

                    # Process cloud cost items
                    for cloud_cost_item in cloud_cost_item_list:

                        # Skip if same service: cost allocation to own service is unwanted
                        if cloud_cost_item.service != cloud_tag_selector_consumer_cost_item.provider_service:

                            # Check if matching service instance was already processed
                            consumer_cost_item_key =\
                                str(selector_nb) + chr(10) +\
                                ServiceInstance.get_id(cloud_cost_item.service, cloud_cost_item.instance)
                            if consumer_cost_item_key in new_consumer_cost_items:

                                # Increase existing cost allocation key with the first cost of this cloud cost item
                                new_consumer_cost_item = new_consumer_cost_items[consumer_cost_item_key]
                                for i in range(nb_allocation_keys):
                                    new_consumer_cost_item.allocation_keys[i] += cloud_cost_item.amounts[0]

                            else:
                                # Create new consumer cost item for this instance
                                # TODO: A partial clone like this should be done in the class itself
                                #       else it becomes very hard to identify when new attributes are added
                                #       that may need to be cloned as well
                                #       Also, this breaks when subclassing with relevant new attributes
                                #      -> Move to ConsumerCostItem class
                                new_consumer_cost_item = self.cost_item_factory.create_consumer_cost_item()
                                new_consumer_cost_item.date_str = cloud_cost_item.date_str
                                new_consumer_cost_item.service = cloud_cost_item.service
                                new_consumer_cost_item.instance = cloud_cost_item.instance
                                new_consumer_cost_item.tags = cloud_tag_selector_consumer_cost_item.tags.copy()
                                new_consumer_cost_item.provider_service = provider_service
                                new_consumer_cost_item.provider_instance = provider_instance
                                # TODO: split and dispatch the provider meter values
                                new_consumer_cost_item.provider_meters =\
                                    cloud_tag_selector_consumer_cost_item.provider_meters.copy()
                                new_consumer_cost_item.provider_cost_allocation_type = \
                                    cloud_tag_selector_consumer_cost_item.provider_cost_allocation_type
                                new_consumer_cost_item.provider_tag_selector =\
                                    cloud_tag_selector_consumer_cost_item.provider_tag_selector
                                for i in range(nb_allocation_keys):
                                    new_consumer_cost_item.allocation_keys[i] += cloud_cost_item.amounts[0]
                                new_consumer_cost_item.provider_cost_allocation_cloud_tag_selector =\
                                    cloud_tag_selector

                                # Add new consumer cost item
                                new_consumer_cost_items[consumer_cost_item_key] = new_consumer_cost_item
                                cost_items.append(new_consumer_cost_item)

        # Log evaluation errors
        for error_key, error_count in evaluation_error_dict.items():
            error_fields = error_key.split(chr(10))
            provider_service = error_fields[0]
            provider_instance = error_fields[1]
            cloud_tag_selector = error_fields[2]
            exception = error_fields[3]
            error("Caught exception '" + exception + "' " + str(error_count) + " times " +
                  "when evaluating ProviderCostAllocationCloudTagSelector '" + cloud_tag_selector +
                  "' of ProviderService '" + provider_service +
                  "' and of ProviderInstance '" + provider_instance + "'" +
                  ", for date " + self.date_str)

        # Clean-up for the sake of memory
        evaluation_error_dict.clear()
        cloud_tag_dict.clear()
        new_consumer_cost_items.clear()

    def process_default_products(self,
                                 cost_items: list[CostItem],
                                 default_product_consumer_cost_items: dict[str, list[ConsumerCostItem]]):

        # Reset instances
        self.reset_instances(cost_items)

        # Calculate default product allocation total keys by provider service
        nb_allocation_keys = self.cost_item_factory.config.nb_allocation_keys
        default_product_allocation_total_keys = {}  # Key = provider service, Value = default product total keys
        for provider_service, default_product_consumer_cost_item_list in default_product_consumer_cost_items.items():
            total_keys = [0.0] * nb_allocation_keys
            default_product_allocation_total_keys[provider_service] = total_keys
            for i in range(nb_allocation_keys):
                for default_product_consumer_cost_item in default_product_consumer_cost_item_list:
                    total_keys[i] += default_product_consumer_cost_item.allocation_keys[i]
                if total_keys[i] == 0:  # If every key is 0, then set every key to 1 (avoid division by 0)
                    for default_product_consumer_cost_item in default_product_consumer_cost_item_list:
                        default_product_consumer_cost_item.allocation_keys[i] = 1
                    total_keys[i] = len(default_product_consumer_cost_item_list)

        # Add default products for consumer cost items with no product
        new_cost_items = []
        for cost_item in cost_items:
            provider_service = cost_item.get_provider_service()
            if (provider_service and
                    not cost_item.get_product() and
                    cost_item.provider_service in default_product_consumer_cost_items):
                for default_product_consumer_cost_item\
                        in default_product_consumer_cost_items[cost_item.provider_service]:
                    new_consumer_cost_item = self.cost_item_factory.create_consumer_cost_item()
                    new_consumer_cost_item.copy(cost_item)
                    new_consumer_cost_item.provider_cost_allocation_type += "+DefaultProduct"
                    default_product_total_keys = default_product_allocation_total_keys[cost_item.provider_service]
                    provider_meter_ratio =\
                        sum(default_product_consumer_cost_item.allocation_keys) / sum(default_product_total_keys)
                    for provider_meter in new_consumer_cost_item.provider_meters:
                        provider_meter.value *= provider_meter_ratio
                    self.update_default_product_from_consumer_cost_item(new_consumer_cost_item,
                                                                        default_product_consumer_cost_item)
                    for i in range(nb_allocation_keys):
                        new_consumer_cost_item.allocation_keys[i] /= default_product_total_keys[i]
                    new_cost_items.append(new_consumer_cost_item)
            else:
                new_cost_items.append(cost_item)

        # Set global default product for self consumption
        default_product = self.cost_item_factory.config.default_product
        if default_product:
            for cost_item in new_cost_items:
                if cost_item.is_self_consumption():
                    if not cost_item.get_product():
                        cost_item.provider_cost_allocation_type += "+DefaultProduct"
                        self.update_default_product_from_config(cost_item)

        # Add consumer cost items with default products for final service instances with no product
        for service_instance in self.service_instances.values():
            if not service_instance.is_provider():
                new_consumer_cost_item = self.cost_item_factory.create_consumer_cost_item()
                new_consumer_cost_item.date_str = self.date_str
                new_consumer_cost_item.provider_service = service_instance.service
                new_consumer_cost_item.provider_instance = service_instance.instance
                new_consumer_cost_item.service = service_instance.service
                new_consumer_cost_item.instance = service_instance.instance
                new_consumer_cost_item.provider_cost_allocation_type = "DefaultProduct"
                new_consumer_cost_item.allocation_keys = [1.0] * nb_allocation_keys
                if service_instance.service in default_product_consumer_cost_items:
                    for default_product_consumer_cost_item\
                            in default_product_consumer_cost_items[service_instance.service]:
                        new_consumer_cost_item_with_product = self.cost_item_factory.create_consumer_cost_item()
                        new_consumer_cost_item_with_product.copy(new_consumer_cost_item)
                        self.update_default_product_from_consumer_cost_item(new_consumer_cost_item_with_product,
                                                                            default_product_consumer_cost_item)
                        new_cost_items.append(new_consumer_cost_item_with_product)
                elif default_product:
                    self.update_default_product_from_config(new_consumer_cost_item)
                    new_cost_items.append(new_consumer_cost_item)

        # Return
        return new_cost_items

    def reset_instances(self, cost_items: list[CostItem]):
        self.service_instances = {}
        for cost_item in cost_items:
            if not cost_item.is_consumer_cost_item_removed_for_cycle():
                cost_item.set_instance_links(self)

    def update_default_product_from_config(self, new_consumer_cost_item: ConsumerCostItem):
        new_consumer_cost_item.product = self.cost_item_factory.config.default_product

    def update_default_product_from_consumer_cost_item(self,
                                                       new_consumer_cost_item: ConsumerCostItem,
                                                       default_product_consumer_cost_item: ConsumerCostItem):
        new_consumer_cost_item.product = default_product_consumer_cost_item.product
        new_consumer_cost_item.product_dimensions = default_product_consumer_cost_item.product_dimensions.copy()
        for i in range(self.cost_item_factory.config.nb_allocation_keys):
            new_consumer_cost_item.allocation_keys[i] *= default_product_consumer_cost_item.allocation_keys[i]

    def untangle_cycles(self,  cost_items: list[CostItem]):

        # Build untangled services and service ranks
        config = self.cost_item_factory.config.config
        untangled_upstream_services = {}
        untangled_service_ranks = {}
        untangled_upstream_service_ranks = {}
        if 'Cycles' in config and 'ServiceUpstreamList' in config['Cycles']:
            rank = 0
            for service_upstream in config['Cycles']['ServiceUpstreamList'].replace("\n", "").split(","):
                service_upstream_split_list = service_upstream.strip().lower().split(":")
                if len(service_upstream_split_list) != 2:
                    error("Ignored malformatted item '" + service_upstream +
                          "' in Configuration [Cycle] ServiceUpstreamList")
                untangled_service = service_upstream_split_list[0]
                untangled_upstream_service = service_upstream_split_list[1]
                untangled_upstream_services[untangled_service] = untangled_upstream_service
                untangled_service_ranks[untangled_service] = rank
                untangled_upstream_service_ranks[untangled_upstream_service] = rank
                rank += 1
        else:
            # No service upstream list: nothing to do
            return cost_items

        # Build new cost items
        new_cost_items = []
        for cost_item in cost_items:
            new_cost_item = cost_item  # Default

            # Check whether it's a consumer cost item
            provider_service = cost_item.get_provider_service()
            if provider_service:

                # Cycle untangling logic:
                # If A with upstream A' precedes B in the service upstream list, then
                # - A is replaced by A' as consumer of B
                # - A is replaced by A' as consumer of B'
                # - B is removed as consumer of A'

                # Check if consumer service has upstream
                untangled_service_rank = untangled_service_ranks.get(cost_item.service)
                if untangled_service_rank is not None:

                    # Check case: - A is replaced by A' as consumer of B (untangled_service_rank is A)
                    untangled_provider_service_rank = untangled_service_ranks.get(provider_service)
                    if untangled_provider_service_rank is not None:
                        if untangled_service_rank < untangled_provider_service_rank:  # A precedes B
                            # A is replaced by A'
                            new_cost_item = self.cost_item_factory.create_consumer_cost_item()
                            new_cost_item.copy(cost_item)
                            new_cost_item.service = untangled_upstream_services.get(cost_item.service)
                    else:
                        # Check case: - A is replaced by A' as consumer of B' (untangled_service_rank is A)
                        untangled_upstream_provider_service_rank =\
                            untangled_upstream_service_ranks.get(provider_service)
                        if untangled_upstream_provider_service_rank is not None:
                            if untangled_service_rank < untangled_upstream_provider_service_rank:  # A precedes B
                                # A is replaced by A'
                                new_cost_item = self.cost_item_factory.create_consumer_cost_item()
                                new_cost_item.copy(cost_item)
                                new_cost_item.service = untangled_upstream_services.get(cost_item.service)
                            else:
                                # Case: - B is removed as consumer of A' (untangled_service_rank is B)
                                # A precedes B
                                # B is removed
                                new_cost_item = None

            # Append new consumer cost item
            if new_cost_item is not None:
                new_cost_items.append(new_cost_item)

        return new_cost_items

    def visit_for_allocation(self,
                             ignore_cost_as_key: bool,
                             increment_amounts: bool,
                             amount_allocation_to_key_indexes: dict[int]) -> None:
        for service_instance in self.service_instances.values():
            service_instance.reset_visit()
        for service_instance in self.service_instances.values():
            visited_service_instance_list = []
            service_instance.visit_for_allocation(visited_service_instance_list,
                                                  ignore_cost_as_key,
                                                  increment_amounts,
                                                  amount_allocation_to_key_indexes)

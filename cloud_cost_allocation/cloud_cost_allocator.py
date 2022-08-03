# coding: utf-8

# Standard imports
from configparser import ConfigParser
from logging import info, error
import re

# Cloud cost allocation imports
from cloud_cost_allocation.cost_items import CloudCostItem, ConsumerCostItem, CostItemFactory, \
    CostItem, ServiceInstance
from cloud_cost_allocation.exceptions import CycleException, BreakableCycleException, UnbreakableCycleException


class CloudCostAllocator(object):
    """
    Allocates cloud costs from a cloud cost reader and cost allocation key readers
    """

    __slots__ = (
        'cost_item_factory',  # type: CostItemFactory
        'config',               # type: ConfigParser
        'service_instances',  # type: dict[ServiceInstance]
    )

    def __init__(self, cost_item_factory: CostItemFactory, config: ConfigParser):
        self.cost_item_factory = cost_item_factory
        self.config = config
        self.service_instances = {}

    def allocate(self, consumer_cost_items: list[ConsumerCostItem], cloud_cost_items: list[CloudCostItem]) -> bool:

        # Create the list of all cost items and process cloud tag selectors
        info("Processing cloud tag selectors")
        cost_items = []
        cost_items.extend(cloud_cost_items)
        for consumer_cost_item in consumer_cost_items:
            if consumer_cost_item.provider_cost_allocation_type == "CloudTagSelector":
                self.process_cloud_tag_selector(cost_items, consumer_cost_item, cloud_cost_items)
            else:
                cost_items.append(consumer_cost_item)

        # Create and add cloud consumer cost item from tags
        info("Creating consumer cost items from tags")
        new_consumer_cost_items = []
        self.create_consumer_cost_items_from_tags(new_consumer_cost_items, cost_items)
        cost_items.extend(new_consumer_cost_items)

        # Check all dates are the same
        date_str = ""
        for cost_item in cost_items:
            if cost_item.date_str:
                date_str = cost_item.date_str
                break # We just need to find one as a reference
        for cost_item in cost_items:
            if date_str != cost_item.date_str:
                error("Found cost items with different dates: " + date_str + " and " + cost_item.date_str)

        # Check all currencies are the same and populate missing ones (currencies are missing for consumer
        # cost items)
        currency = ""
        for cost_item in cost_items:
            if cost_item.currency:
                currency = cost_item.currency
                break # We just need to find one as a reference
        for cost_item in cost_items:
            if not cost_item.currency:
                cost_item.currency = currency
            else:
                if currency != cost_item.currency:
                    error("Found cost items with different currencies: " + currency + " and " + cost_item.currency)
                    return False

        # Break cycles
        # When a cycle is broken, ConsumerCostItem.is_removed_from_cycle is set to True at the cycle break point
        if not self.break_cycles(cost_items):
            return False

        # Protect against unexpected cycles
        try:

            # Initialize instances and set cost item links
            self.service_instances = {}
            for cost_item in cost_items:
                if not cost_item.is_consumer_cost_item_removed_for_cycle():
                    cost_item.set_instance_links(self)

            # Compute service amortized cost, ignoring the keys that are using cost, and then
            # set these keys from the computed cost
            info("Allocating costs, ignoring keys that are costs")
            self.visit_for_allocation(True, True, False)
            for service_instance in self.service_instances.values():
                for cost_item in service_instance.cost_items:
                    cost_item.set_cost_as_key(service_instance.cost)

            # Allocate amortized costs for services
            info("Allocating amortized costs for services")
            self.visit_for_allocation_and_set_allocated_cost(True, False)

            # Allocate on-demand costs for services
            info("Allocating on-demand costs for services")
            self.visit_for_allocation_and_set_allocated_cost(False, False)

            # Allocate amortized costs for products
            info("Allocating amortized costs for products")
            self.visit_for_allocation_and_set_allocated_cost(True, True)

            # Allocate on-demand costs for products
            info("Allocating on-demand costs for products")
            self.visit_for_allocation_and_set_allocated_cost(False, True)

        except CycleException:
            return False

        return True

    def break_cycles(self, cost_items: list[CostItem]) -> bool:

        # Build service precedence list
        service_precedence_list = []
        if 'Cycles' in self.config and 'ServicePrecedenceList' in self.config['Cycles']:
            for service in self.config['Cycles']['ServicePrecedenceList'].split(","):
                service_precedence_list.append(service.strip().lower())

        # Get max cycle breaks
        max_breaks = 10  # Default value
        if 'Cycles' in self.config and 'MaxBreaks' in self.config['Cycles']:
            max_breaks = int(self.config['Cycles']['MaxBreaks'])

        # Break cycles
        nb_breaks = 0
        while nb_breaks < max_breaks:

            # Log
            info("Detecting and breaking cycles: pass " + str(nb_breaks))

            # Initialize instances and set cost item links
            self.service_instances = {}
            for cost_item in cost_items:
                if not cost_item.is_consumer_cost_item_removed_for_cycle():
                    cost_item.set_instance_links(self)

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
            error("Max number of cost allocation cycle breaks was reached")
            return False

    def create_consumer_cost_items_from_tags(self,
                                             new_consumer_cost_items: list[ConsumerCostItem],
                                             cost_items: list[CostItem]) -> None:

        # Check if consumer tag is used and process cost items
        if 'ConsumerService' in self.config['TagKey'] or 'Product' in self.config['TagKey']:
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
                if consumer_service == "-":  # Ignore consumer service named "-"
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
                # TODO: product dimension
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
                    new_consumer_cost_item.provider_cost_allocation_key = 1.0
                    new_consumer_cost_item.product = product

                    # Add consumer dimensions
                    if 'Dimensions' in self.config['General']:
                        for dimension in self.config['General']['Dimensions'].split(','):
                            consumer_dimension = 'Consumer' + dimension.strip()
                            if consumer_dimension in self.config['TagKey']:
                                for consumer_dimension_tag_key in self.config['TagKey'][consumer_dimension].split(","):
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
            if cloud_cost_item.service != consumer_cost_item.provider_service and \
                    cloud_cost_item.matches_cloud_tag_selector(cloud_tag_selector, consumer_cost_item.provider_service):

                # Check if matching service instance was already processed
                if consumer_service_instance_id in new_consumer_cost_items:

                    # Increase existing cost allocation key with the amortized cost of this cloud cost item
                    new_consumer_cost_item = new_consumer_cost_items[consumer_service_instance_id]
                    new_consumer_cost_item.provider_cost_allocation_key += cloud_cost_item.cloud_amortized_cost

                else:
                    # Create new consumer cost item for this instance
                    # TODO: A partial clone like this should be done in the class itself
                    #       else it becomes very hard to identify when new attributes are added that may need to be cloned as well
                    #       Also, this breaks when subclassing with relevant new attributes
                    #      -> Move to ConsumerCostItem class
                    new_consumer_cost_item = self.cost_item_factory.create_consumer_cost_item()
                    new_consumer_cost_item.date_str = cloud_cost_item.date_str
                    new_consumer_cost_item.service = cloud_cost_item.service
                    new_consumer_cost_item.instance = cloud_cost_item.instance
                    new_consumer_cost_item.tags = consumer_cost_item.tags.copy()
                    new_consumer_cost_item.provider_service = consumer_cost_item.provider_service
                    new_consumer_cost_item.provider_instance = consumer_cost_item.provider_instance
                    # TODO: dimension tags are ignored; should we create different consumer cost items for
                    #  different dimensions?
                    # TODO: split and dispatch the provider meter values based on amortized costs
                    new_consumer_cost_item.provider_meters = consumer_cost_item.provider_meters.copy()
                    new_consumer_cost_item.provider_cost_allocation_type = \
                        consumer_cost_item.provider_cost_allocation_type
                    new_consumer_cost_item.provider_tag_selector = consumer_cost_item.provider_tag_selector
                    new_consumer_cost_item.provider_cost_allocation_key = cloud_cost_item.cloud_amortized_cost
                    new_consumer_cost_item.provider_cost_allocation_cloud_tag_selector = \
                        consumer_cost_item.provider_cost_allocation_cloud_tag_selector

                    # Add new consumer cost item
                    new_consumer_cost_items[consumer_service_instance_id] = new_consumer_cost_item
                    cost_items.append(new_consumer_cost_item)

    def visit_for_allocation_and_set_allocated_cost(self, is_amortized_cost: bool, is_for_products: bool) -> None:

        # Visit, using cost keys, which have been previously computed
        self.visit_for_allocation(False, is_amortized_cost, is_for_products)

        # Set allocated costs
        for service_instance in self.service_instances.values():
            for cost_item in service_instance.cost_items:
                cost_item.set_allocated_cost(is_amortized_cost, is_for_products)

    def visit_for_allocation(self, ignore_cost_as_key: bool, is_amortized_cost: bool, is_for_products: bool) -> None:
        for service_instance in self.service_instances.values():
            service_instance.reset_visit_for_allocation(is_for_products)
        for service_instance in self.service_instances.values():
            visited_service_instance_list = []
            service_instance.visit_for_allocation(visited_service_instance_list,
                                                  ignore_cost_as_key,
                                                  is_amortized_cost,
                                                  is_for_products)

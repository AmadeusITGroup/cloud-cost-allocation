# coding: utf-8

from configparser import ConfigParser
from datetime import date
from logging import error
import re

from cloud_cost_allocation.cloud_cost_allocator import CostItemFactory, CloudCostItem
from cloud_cost_allocation.reader.base_reader import GenericReader


class AzureEaAmortizedCostReader(GenericReader):
    """
    Reads Azure Enterprise Agreement amortized cloud costs.

    Note: The date field in Azure cost exports is in MM/DD/YYYY format
    """
    def __init__(self, cost_item_factory: CostItemFactory, config: ConfigParser):
        super().__init__(cost_item_factory, config)

    def read_item(self, line) -> CloudCostItem:
        # Initiate cloud cost item
        cloud_cost_item = self.cost_item_factory.create_cloud_cost_item()

        # Set date
        azure_date_str = line["Date"].strip()
        if not re.match('\d\d/\d\d/\d\d\d\d', azure_date_str):
            error("Expected Azure date format MM/DD/YYYY, but got: " + azure_date_str)
            return None
        azure_date = date(int(azure_date_str[6:]), int(azure_date_str[:2]), int(azure_date_str[3:5]))
        cloud_cost_item.date_str = azure_date.strftime(self.config['General']['DateFormat'])

        # Set amortized cost
        cloud_cost_item.cloud_amortized_cost = float(line["CostInBillingCurrency"])

        # Compute and set on-demand cost
        # https://docs.microsoft.com/en-us/azure/cost-management-billing/reservations/understand-reserved-instance-usage-ea
        if line["ReservationId"]:
            if line["ChargeType"] == "UnusedReservation":
                cloud_cost_item.cloud_on_demand_cost = 0.0  # Unused reservations are not on-demand costs
            else:
                cloud_cost_item.cloud_on_demand_cost = float(line["Quantity"])*float(line["UnitPrice"])
        else:
            cloud_cost_item.cloud_on_demand_cost = cloud_cost_item.cloud_amortized_cost

        # Set currency
        cloud_cost_item.currency = line["BillingCurrencyCode"]

        # Process tags
        for tag in line["Tags"].split('","'):
            if tag:
                key_value_match = re.match("\"?([^\"]+)\": \"([^\"]*)\"?", tag)
                if key_value_match:
                    key = key_value_match.group(1).strip().lower()
                    value = key_value_match.group(2).strip().lower()
                    cloud_cost_item.tags[key] = value
                else:
                    error("Unexpected tag format in cost stream: '" + tag + "'")

        # Process unused reservation
        if line['ChargeType'] == 'UnusedReservation':
            cloud_cost_item.service = self.config['AzureEaAmortizedCost']['UnusedReservationService']
            if 'UnusedReservationInstance' in self.config['AzureEaAmortizedCost']:
                cloud_cost_item.instance = self.config['AzureEaAmortizedCost']['UnusedReservationInstance']
            else:
                cloud_cost_item.instance = cloud_cost_item.service
            if 'Dimensions' in self.config['General']:
                for dimension in self.config['General']['Dimensions'].split(','):
                    unused_reservation_dimension = 'UnusedReservation' + dimension.strip()
                    if unused_reservation_dimension in self.config['AzureEaAmortizedCost']:
                        cloud_cost_item.dimensions[dimension] =\
                            self.config['AzureEaAmortizedCost'][unused_reservation_dimension]

        else:
            # Fill cost item from tags
            cloud_cost_item.fill_from_tags(self.config)

        return cloud_cost_item


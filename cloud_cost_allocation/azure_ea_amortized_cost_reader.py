# coding: utf-8

from csv import DictReader
from cloud_cost_allocation import cloud_cost_allocator
from configparser import ConfigParser
from datetime import date
from logging import error
import re
import validators
import requests


class AzureEaAmortizedCostReader(object):
    """
    Reads Azure Enterprise Agreement amortized cloud costs
    """

    __slots__ = (
        'config',             # type: ConfigParser
        'cost_item_factory',  # type: cloud_cost_allocator.CostItemFactory
    )

    def __init__(self, cost_item_factory: cloud_cost_allocator.CostItemFactory, config: ConfigParser):
        self.config = config
        self.cost_item_factory = cost_item_factory

    def read(self, cost_items: list[cloud_cost_allocator.CloudCostItem], cloud_cost_key: str) -> None:
        if validators.url(cloud_cost_key):
            response = requests.get(cloud_cost_key)
            reader = DictReader(response.iter_lines())
            self.read_stream(cost_items, reader)
        else:
            with open(cloud_cost_key, 'r') as cloud_cost_key_text_io:
                reader = DictReader(cloud_cost_key_text_io)
                self.read_stream(cost_items, reader)

    def read_stream(self, cost_items: list[cloud_cost_allocator.CloudCostItem], reader: DictReader) -> None:

        # Read cost lines
        for line in reader:

            # Initiate cloud cost item
            cloud_cost_item = self.cost_item_factory.create_cloud_cost_item()

            # Set cloud cost line
            cloud_cost_item.cloud_cost_line = line

            # Set date
            azure_date_str = line["Date"].strip()
            if not re.match('\d\d/\d\d/\d\d\d\d', azure_date_str):
                error("Expected Azure date format MM/DD/YYYY, but got: " + azure_date_str)
                continue
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

            # Add cloud cost item
            cost_items.append(cloud_cost_item)


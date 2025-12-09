# coding: utf-8

from datetime import date
from dateutil import parser
from dateutil.relativedelta import relativedelta
from logging import fatal
import re

from cloud_cost_allocation.cloud_cost_allocator import CostItemFactory, CloudCostItem
from cloud_cost_allocation.reader.base_reader import GenericReader
from cloud_cost_allocation.utils import utils


class CSV_FocusReader(GenericReader):
    """
    Reads cloud costs in FOCUS CSV format
    """
    def __init__(self, cost_item_factory: CostItemFactory):
        super().__init__(cost_item_factory)

    def read_item(self, line) -> CloudCostItem:

        # Create cloud cost item
        cloud_cost_item = self.cost_item_factory.create_cloud_cost_item()

        # The charge period must be one day, which is parsed as the date
        charge_period_start_date_str = line["ChargePeriodStart"]
        try:
            charge_period_start_date = parser.parse(charge_period_start_date_str)
        except(parser.ParserError, OverflowError):
            fatal("Invalid FOCUS ChargePeriodStart in line %s", line)
            return None
        charge_period_end_date_str = line["ChargePeriodEnd"]
        try:
            charge_period_end_date = parser.parse(charge_period_end_date_str)
        except(parser.ParserError, OverflowError):
            fatal("Invalid FOCUS ChargePeriodEnd in line %s", line)
            return None
        if relativedelta(charge_period_end_date, charge_period_start_date) != relativedelta(days=+1):
            fatal("Expected Charge Period to be exactly 1 day; line %s", line)
            return None
        config = self.cost_item_factory.config
        cloud_cost_item.date_str = charge_period_start_date.strftime(config.date_format)

        # Set amortized cost, which is effective cost in FOCUS
        if 'AmortizedCost' in config.amounts:
            effective_cost = line["EffectiveCost"]
            if utils.is_float(effective_cost):
                cloud_cost_item.amounts[config.amounts.index('AmortizedCost')] = float(effective_cost)
            else:
                fatal("EffectiveCost cannot be parsed in line %s", line)
                return None

        # Compute and set on-demand cost, which is contracted cost in FOCUS
        on_demand_cost = 0.0
        if 'OnDemandCost' in config.amounts:
            contracted_cost = line["ContractedCost"]
            if utils.is_float(contracted_cost):
                cloud_cost_item.amounts[config.amounts.index('OnDemandCost')] = float(contracted_cost)
            else:
                fatal("ContractedCost cannot be parsed in line %s", line)
                return None

        # Set currency
        cloud_cost_item.currency = line["BillingCurrency"]

        # Process tags
        tags = line["Tags"].strip().lower()
        if tags != "null":
            tags_match = re.match("{(.*)}", tags)
            if not tags_match:
                fatal("Invalid Tags format in line %s: ", line)
                return None
            for tag in tags_match.group(1).split(','):
                if tag:
                    key_value_match = re.match("\s*\"([^\"]+)\"\s*:\s*\"?([^\"]*)\"?\s*", tag)
                    if key_value_match:
                        key = key_value_match.group(1).strip()
                        value = key_value_match.group(2).strip()
                        cloud_cost_item.tags[key] = value
                    else:
                        fatal("Unexpected tag format: '" + tag + "' in line %s", line)

        # Process unused commitment
        config = self.cost_item_factory.config
        if line["CommitmentDiscountStatus"] == "Unused":
            cloud_cost_item.service = config.config['FocusUnusedCommitment']['UnusedCommitmentService']
            if 'UnusedCommitmentInstance' in config.config['FocusUnusedCommitment']:
                cloud_cost_item.instance = config.config['FocusUnusedCommitment']['UnusedCommitmentInstance']
            else:
                cloud_cost_item.instance = cloud_cost_item.service
            for dimension in config.dimensions:
                unused_commitment_dimension = 'UnusedCommitment' + dimension
                if unused_commitment_dimension in config.config['FocusUnusedCommitment']:
                    cloud_cost_item.dimensions[dimension] =\
                        config.config['FocusUnusedCommitment'][unused_commitment_dimension]

        else:  # Not an unused commitment

            # Fill cost item from tags
            self.fill_from_tags(cloud_cost_item)

            # Set default service
            if not cloud_cost_item.service:
                cloud_cost_item.service = config.default_service

            # Set default instance
            if not cloud_cost_item.instance:
                cloud_cost_item.instance = cloud_cost_item.service

        return cloud_cost_item

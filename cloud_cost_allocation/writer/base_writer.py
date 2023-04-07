'''
Created on 21.04.2022

@author: marc.diensberg
'''
from abc import ABC, abstractmethod
from logging import error

from cloud_cost_allocation.cost_items import Config, ServiceInstance, ConsumerCostItem, CloudCostItem, CostItem


class GenericWriter(ABC):
    '''
    classdocs
    '''

    __slots__ = (
        'config',               # type: Config
        'service_instances',    # type: ServiceInstance
        'exporters',            # type: dict[type -> method]
    )

    def __init__(self, service_instances: list[ServiceInstance], config: Config):
        '''
        Constructor
        '''
        self.service_instances = service_instances
        self.config = config
        self.exporters = {}
        self.exporters[CostItem] = self.export_item_base
        self.exporters[CloudCostItem] = self.export_item_cloud
        self.exporters[ConsumerCostItem] = self.export_item_consumer

    @abstractmethod
    def get_headers(self) -> list[str]:
        pass

    @abstractmethod
    def export_item_base(self, cost_item, service_instance) -> dict[str]:
        pass

    def export_item_cloud(self, cost_item, service_instance) -> dict[str]:
        return self.export_item_base(cost_item, service_instance)

    @abstractmethod
    def export_item_consumer(self, cost_item, service_instance) -> dict[str]:
        return self.export_item_base(cost_item, service_instance)

    def export_item(self, cost_item, service_instance) -> dict[str]:
        item_type = type(cost_item)
        exporter = self.exporters.get(item_type)
        if exporter:
            return exporter(cost_item, service_instance)
        else:
            # Requires python 3.7+ where dict preserves insertion order
            # OrderedDict could be used in older versions
            priorized_exporters = list(self.exporters.keys())
            priorized_exporters.reverse()
            for exporter in priorized_exporters:
                if isinstance(cost_item, exporter):
                    return self.exporters[exporter](cost_item, service_instance)

        error("No exporter found for type " + str(item_type))
        return None

    def write_item(self, writer, cost_item, service_instance) -> None:
        data = self.export_item(cost_item, service_instance)
        writer.writerow(data)

    def write(self, writer) -> None:
        # Process cost items ordered by service instance
        for service_instance_id in sorted(self.service_instances.keys()):
            service_instance = self.service_instances[service_instance_id]
            for cost_item in service_instance.cost_items:
                self.write_item(writer, cost_item, service_instance)

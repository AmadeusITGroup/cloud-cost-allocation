# Cloud cost allocation

## General
Mainstream cost management tools from vendors and from cloud providers use the following information available in billing data, in order to allocate costs:
- *Resource containers*, like *Projects* in *Google Cloud Platform*, or *Subscriptions* and *Resource Groups* in *Azure*. For example, the cost of a given Azure subscription can be allocated to a given a cost center and business unit. 
- *Tags*. For example, the cost of cloud resources tagged with *cost_center:1234* and *business_unit:Digital* are allocated to the *Cost Center 1234* and to the *Digital Business Unit*.

Such cost allocation methods do not address *hierarchical consumption*, where different workloads operated by different DevOps teams within the same company consume one another, a.k.a. *shared services* with multiple sharing levels. Such cost allocation methods do not also support the fact that some technical applications can serve different commercial products. In such a case, every product should be allocated a share of the cost of every application the product uses.

![Hierarchical service consumption example](./puml/hierarchical-service-consumption-example.svg)

The cost allocation model proposed here supports such consumption hierarchy. Usage is taken into account: the more you use a service, the more you get cost allocated from it, the more you should optimize your usage of it. What's the unit of usage? It's up to the service owner to say. Conceptually, this unit should relate to the FinOps North Star Metrics of the service, i.e. a functional metric that measures the throughput of the service and grows along with the cost.

![Hierarchical service consumption example](./puml/hierarchical-service-cost-allocation-example.svg)

## Definitions

|Term|Definition|
|---|---|
|*Service*|A technical workload, operated by DevOps, which can run on the cloud and/or consume other services. The model makes no distinction between low-level services like a container platform and application services like a Web service: both are technical workloads operated by DevOps teams.|
|*Product*|A commercial product, which uses one or multiple services. Products are somehow commercial packaging of services under the control of Product Managers.|
|*Provider Service*|A service that is consumed by another other service or product, a.k.a. a shared service.|
|*Consumer Service*|A service that consumes another service.|
|*Instance*|The running instance of a service. If we think of *Services* as *Classes* in object-oriented programming, then *Instances* would be the *Objects*.|
|*Dimension*|A dimension in the cost allocation, for example environment like test or prod.|
|*Partition*|The running partition of a service, used to load balance the traffic or to shard data.|
|*Component*|A component within the architecture of a service.|
|*Meter*|A meter to measure the functional throughput of a service, a.k.a. *FinOps North Star Metric*.|
|*Amortized Cost*|The billing cost incremented with the amortized cost of the reservation purchase.|
|*On-demand Cost*|The equivalent on-demand cost, i.e. as if no reservation purchase has been made.|
|*Cost Item*|A cost that is either a cloud resource cost or a cost allocated by a provider service.|
|*Cost Allocation Key*|A quantity to allocate a share of a cost. Cost share = cost * key / total keys.|
|*Cost Allocation Item*|A Cost Item coming from a Cost Allocation Key.|

## UML Class Diagram

Keep calm and drink coffee.

![Hierarchical service consumption example](./puml/cost-allocation-model.svg)

## Model principles and considerations

1. The model does not rely on resource containers (GCP projects, Azure Subscriptions, ...), but only on cloud resource tags, in order to work transparently for all cloud providers. 

2. On top of tags, the model uses cost allocation data to be provided by Service owners.
  * If a Service owner provides no cost allocation data, the Service keeps its cost for itself.
  * Cost allocation is based on keys: the cost of a service is split and dispatched proportionally to cost allocation keys. 
  * Ideally, all cloud costs should be allocated to Products. This means every Service Owner should provide cost allocation data to allocate the Service cost to consumer Services or Products.

3. Services, Products and North Star Metrics are discovered through tags and cost allocation data.
  * Products and services are set to lower case at data ingestion.
  * Data quality can be achieved by pre-processing data and checking it against Product and Service catalogs, which is not covered here.

4. The pivot of the cost allocation is Instances.
  * Every Service owner should define properly the Service Instances to be in position to generate cost allocation data for each of them.
  * Dimensions are not structuring the cost allocation but rather intended to serve as commonly used dimensions for cost reporting.

5. Both Products and Services have their North Star Metrics.
   * Service North Star Metrics, which are to be defined by DevOps, are useful to monitor the cost efficiency of Services and to drive the cost allocation to Consumer Services.
   * Product North Star Metrics, which are to be defined by Product Managers, are useful to monitor the cloud cost health of Products and to take business decisions.
   * Service North Star Metrics can be a combination (*ProviderMeterName1*, *ProviderMeterName2*, ...).
     * For example, a North Star Metric of a container service could be the combination of container CPU request and container Memory request: the Cost Allocation Keys should reflect the two.
     * Another example is a data lake with multiple consumers, i.e. a shared data lake. The cost of the data lake will grow essentially with the data size. The North Star Metric reported in cost allocation data for every consumer could be the combination of the data lake size share of the consumer, which is not predictable to the consumer but is driving the cost allocation, and of the actually consumed data size, which is predictable for the consumer and useful to report, in order to enable consumer cost optimization. 
   * A Product or a Service can have multiple North Star Metrics, corresponding to different Cost Allocation Items. For example, a container service can have a North Star Metric for the compute cost and another North Star Metric for the storage, which represent two independent cost scaling dimensions.

6. Cost items are tagged.
   * Cost Item tags come from cloud resource tags and from consumer tags in cost allocation data.
   * Tags are not only useful in cost reporting, but they can be used to structure the cost allocation thanks to *ProviderTagSelector*. You can see an example in the test `test1`.
   * Note that Dimensions can be seen conceptually as specific Tags that have been promoted as first-class citizens in the model for cost reporting.
    
7. A Cost Allocation Item can allocate cost both to a Service and to a Product.
  * Service cost allocation and product cost allocation work in parallel. The test `test2` illustrates how these cost allocation flows work together.
  * Service cost allocation basically propagates costs through Cost Allocation Keys. The cost of a Service is made of the costs of cloud resources it uses directly and of the cost shares of the other Services it consumes.  
  * Unlike Service cost allocation, Product cost allocation propagates only costs that have not been allocated yet to Products in the downstream cost allocation hierarchy.
  * Assuming that all cloud resources are properly tagged and that Services eventually allocate all their costs to Products, the cost of all cloud resources must be equal to the cost of all products.
    
8. Both On-demand Costs and Amortized Costs are part of the model.
  * Reporting the two is useful for Service owners (DevOps) and Product Managers to see the savings made thanks to the reservation purchases.
  * In other words, using SKUs in the Reservation Green/Red zones defined by the FinOps team is a cost rate optimization by DevOps, whose benefit can be simply reported as: Reservation saving = On-Demand Cost - Amortized Cost.

9. Cost allocation cycles are not supported. When cycles are detected, they are broken.

## Bittersweet ways for a service to allocate its cost

The basic way for a service to allocate its cost is to provide cost allocation data containing cost allocation keys to split and to dispatch the cost between the consumers.
There are alternatives:
- Use specific configurable *consumer tags*.
- Use specific *cost allocation type* in cost allocation data.

### Consumer tag

Specific configurable tags can be used by a service to allocate its cost to consumers.
Consumer tags are convenient to get cost allocation keys generated automatically based on tagging.
Technically, for every *CostItem* having consumer tags, a new *ConsumerCostItem* is created with:
- *ProviderService* and *ProviderInstance*: the ones from the *CostItem*.
- *ConsumerService* and *ConsumerInstance*: the ones from the consumer tags.
- *ProviderTagSelector*: an expression matching the consumer tags
- *ProviderCostAllocationKey*: value 1.0
An example is available in the test `test3`.

### Cost allocation types in cost allocation data

The default value of *ProviderCostAllocationType* in cost allocation data is *'Key'*.
Two other types of cost allocation are supported. They should be used on purpose, as they are quite tricky:
- *'CloudTagSelector'*. The consumer service instances are not explicitly specified in the cost allocation data: they are inferred as the ones consuming the cloud cost items whose tags match the *ProviderCostAllocationCloudTagSelector* expression. 
The cost allocation keys are set as the amortized costs of the matching cloud cost items.
This type of cost allocation is convenient to allocate costs to consumer services that run directly on the cloud proportionally to their cloud costs. 
- *'Cost'*. The cost is allocated to the consumer services proportionally to their amortized costs.
Technically, amortized costs are globally allocated to service instances a first time, in ignoring this type of cost allocation.
The amortized costs resulting from this cost allocation are then used as cost allocation keys to perform the actual cost allocation. 
Although this type of cost allocation is convenient to avoid bothering about cost allocation keys, it can produce results that are hardly predictable and understandable, depending on the complexity of the global cost allocation hierarchy.

Examples of *'CloudTagSelector'* and *'Cost'* are available in the test `test3`.

An even more general type of cost allocation could be considered:
- *'ConsumerTagSelector'*. Cost would be allocated to service instances whose cost items match the *ProviderCostAllocationConsumerTagSelector* expression proportionally to their amortized costs.
Maybe it is too tricky, and it was not needed so far!

## Test

Run the following command in the repository root directory:

```
python -m unittest -v tests.test
```

## Usage

The code for the command line in `main.py` is a basic example to:
- Read cloud costs
- Read cost allocation keys
- Allocate costs
- Write allocated costs

The `test.py` file in the `tests` directory illustrates how to add custom code and columns in the allocated costs.

## Contributing 

### Bug reports
Bugs are both proofs of success and of failure: what do you think?
Before submitting a bug, please check through the [GitHub issues](https://github.com/AmadeusITGroup/cloud-cost-allocation/issues),
both open and closed, to confirm that the bug hasn't been reported before.

### Feature requests
If you think a feature is missing and could be useful in this module, feel free to raise a feature request through the
[GitHub issues](<https://github.com/AmadeusITGroup/JumpSSH/issues>).
Please keep in mind that the cost allocation model is intended to be as minimal as possible.

### Code contributions
When contributing code, please follow [this project-agnostic contribution guide](<http://contribution-guide.org/>).

### TODO

- Cost readers for GCP and AWS.
- Breaking of cost allocation cycles before the cost allocation visit.

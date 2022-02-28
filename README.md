# Cloud cost allocation

## General
Standard cloud provider and vendor cost management tools rely on the following data sources available in billing data:
- *Resource containers*, like *Projects* in *Google Cloud Platform*, or *Subscriptions* and *Resource Groups* in *Azure*. For example, the cost of cloud resources hosted in a given Azure subscription can be allocated to a given organization or cost center. 
- *Tags*. For example, the cost of cloud resources tagged with *cost_center:1234* are allocated to the *Cost Center 1234*.

Such cost allocation methods do not address *hierarchical service consumption*, where services are deployed and operated by different teams within the same company (a.k.a. *shared services* with multiple sharing levels): 

![Hierarchical service consumption example](./puml/hierarchical-service-consumption-example.svg)

Such consumption hierarchy has to be reflected in the cost allocation. Note that the cost allocation of a service should not be arbitrary, but based on usage, in order to incentivize usage optimization. The more you use a service, the more you get cost allocated from it, the more you should optimize your usage of it. This OpenSource code proposes a cost allocation model that supports any arbitrary consumption hierarchy. Furthermore, this cost allocation model implements the FinOps Unit Economics approach for shared services: shared service owners should define North Star Metrics, which measure the functional throughput of their services and serve as usage units for their consumers.    

![Hierarchical service consumption example](./puml/hierarchical-service-cost-allocation-example.svg)

## Definitions

|Term|Definition|
|---|---|
|*Product*|A commercial product, which uses one or multiple services.|
|*Service*|A technical workload, operated by DevOps, which can run on the cloud and/or use other services.|
|*Provider Service*|A services that is consumed by another other service, a.k.a. a shared service.|
|*Consumer Service*|A service that consumes another service.|
|*Instance*|The running instance of a service. If we compare *Services* to *Classes* in object-oriented programming, then *Instances* would be the *Objects*.|
|*Environment*|The running environment of a service in the development cycle, typically: dev, test, and prod.|
|*Partition*|The running partition of a service, used to load balance the traffic or to shard data.|
|*Component*|A component within the architecture of a service.|
|*Meter*|A meter to measure the functional metric of service, a.k.a. North Star Metric.|
|*Amortized cost*|The billing cost incremented with the amortized cost of the reservation purchase.|
|*On-demand cost*|The equivalent on-demand cost, i.e. as if no reservation purchase has been made.|
|*Cost item*|A cost that is either a cloud provider cost or a cost allocated by a provider service.|

## UML CLass Diagram

Keep calm amd drink coffee!

![Hierarchical service consumption example](./puml/cost-allocation-model.svg)

## Model principles and considerations

## Test

## Example

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
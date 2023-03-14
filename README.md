# Cloud cost allocation

## Overview
This project provides tools for **shared, hierarchical cost allocation** based on user-defined usage metrics.

## Introduction
**Mainstream** cloud cost management **tools** from the Cloud Service Providers or 3rd party vendors typically **rely on** the high level hierarchy of cloud objects (*Resource containers*, like **Projects** in *Google Cloud Platform*, or **Subscriptions** and *Resource Groups* in *Azure*) or **tags to allocate costs** to a given cost center or business unit.
In addition, some tools support one level of cost re-allocation (e.g. based on fixed percentages, overall/specific costs of the consumers). Usually, this does not include the ability to use dynamic, custom defined metrics though.
As a result, the cost allocation process of shared services is often rather:
- **Imprecise**, thus unfair, since cost allocation is not done based on the actual consumption
- **Incomplete**, since shared costs, especially if hierarchical, are simply not allocated to their consumers, thus requiring additional tooling on top
- **Opaque** and thus hard to action, since neither the key cost drivers nor their actual consumption (and thus angles for optimization) are visible to the consumers

### Example
![Hierarchical cloud consumption example](https://github.com/AmadeusITGroup/cloud-cost-allocation/raw/main/puml/hierarchical-service-consumption-example.svg)

In this example, classic, usage-based cost allocation would likely stop at the cloud resource level. Thus, only the container service would be visible. With additional instrumentation these costs could be split into the direct costs for each of the services running on it. But the costs of the shared monitoring or history service would not be properly allocated, let alone their contributions to the business services behind that.
This might not be a problem as long as those costs are small and the hierarchy of services using each other is shallow. But in large production environments the key cost drivers for a given business service might thus be hidden making it very difficult to assess the total costs of a given service.
Usually, the only way to resolve this issue is avoid sharing services by duplicating them. While this can work in some cases it often also results in higher overall costs, both for deploying and for managing these services.

The goal of the cost allocation model proposed here is to support such complex consumption hierarchies in a usage-based fashion with custom (North Star) Metrics up the business service level.
This does not only enable the more accurate and complete cost allocation required to make proper business decisions and forecasts, but also yields more actionable outputs thanks to the transparency on unit costs, consumption and their evolution over time.
Furthermore, this also allows service owners to easily identify their main cost drivers in the service hierarchy. This in turn helps to ensure that optimization efforts can be focused on the most promising services as well as to simulate and later measure the actual benefits this can bring to all services along the consumption chain.

![Hierarchical cloud git commit -m cost allocation example](https://github.com/AmadeusITGroup/cloud-cost-allocation/raw/main/puml/hierarchical-service-cost-allocation-example.svg)

## Definitions

| Term                  | Definition                                                                                                                                                       |
|-----------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| *Service*             | A technical workload, operated by DevOps, which can either run directly on the cloud, or consume other services, or both.                                        |
| *Product*             | A business product, which relies on one or multiple services. Products are somehow commercial packaging of services under the control of Product Managers.       |
| *Product Dimension*   | An optional dimension for the cost report of a product, for example: a product feature, a product flavor, a market or a market segment.                          |
| *Provider Service*    | The role of a service when it is consumed by another other service or product, a.k.a. a shared service.                                                          |
| *Consumer Service*    | The role of a service when it consumes another service.                                                                                                          |
| *Instance*            | A running instance or a deployment of a service. If we think of *Services* as *Classes* in object-oriented programming, then *Instances* would be the *Objects*. |
| *Dimension*           | An optional dimension in the cost allocation, for example an environment like Test or Production, or a component in the architecture of the service.             |
| *Meter*               | A meter that measures the functional activity or throughput of a service or of a product.                                                                        |
| *Amortized Cost*      | The billing cost incremented with the amortized cost of the reservation purchases.                                                                               |
| *On-demand Cost*      | The equivalent on-demand cost, i.e. as if no reservation purchase had been made.                                                                                 |
| *Cost Item*           | A cost that is either coming from cloud provider billing or allocated by a provider service.                                                                     |
| *Cost Allocation Key* | A numerical value to allocate a share of a cost. Cost share = cost * key / total keys.                                                                           |

## UML Class Diagram

Keep calm and drink coffee.

![Cloud cost allocation model](https://github.com/AmadeusITGroup/cloud-cost-allocation/raw/main/puml/cost-allocation-model.svg)

## Model principles and considerations

1. The model relies solely on cloud resource tags in order to work transparently for all cloud providers
    * Note that policies can be used to propagate tags from cloud provider containers (GCP Projects, Azure Subscriptions or Resource Groups, ...) to individual resources if required
2. On top of that, the model uses cost allocation data provided by the service owners
    * If a service owner provides no cost allocation data, the service becomes a leaf in the hierarchy and thus owns all costs allocated along the chain
    * Cost allocation data is based on keys: the cost of a service is split and dispatched proportionally to cost allocation keys
    * Ideally, all cloud costs should be allocated to products. This means every service owner should provide cost allocation data to allocate the service cost to consumer services and/or products
3. Services, products and meters are discovered and linked through tags and through cost allocation data
    * It is strongly recommended to use policies or other means to cross-check these names against the relevant product and service catalogs
4. The pivot of the cost allocation is the *Instance*: service cost allocation data is per instance 
    * Service owners should design carefully service instances, in order to be able to generate cost allocation data for each of them
    * Naming conventions are recommended to reflect the design of service instance, and possibly to provide some information about every service instance
    * All other dimensions (e.g. environment) are not structuring for the cost allocation between instances, but they provide commonly used dimensions for cost reporting
5. Both products and services have their meters
    * Product meters are defined by product owners (or mangers), while service meters are defined by service owners
    * A product meter measures the business volume served by the product
    * Product meters are used to monitor cost efficiency at product level, to perform cloud cost forecast in budget activities, to optimize pricing, and more generally to take data-driven business decisions
    * A service meter measures the usage of a provider service by consumer services and products, and so it must be reflected in cost allocation keys 
    * Service meters are used to monitor cost efficiency, to detect drifts, to track the benefit of cloud cost optimizations, and more generally to serve as KPIs for service cloud costs
    * A given product or service can have more than one meter
        * Example 1: container service
            * A meter of a container service could be the combination of container CPU request and container Memory request
            * In this case the Cost Allocation Keys be computed out of the two metrics
        * Example 2: shared data lake
            * Here the cost driver could be the amount of data being stored
            * Since this volume is hard to predict and optimize, this could be further broken down into the daily volume stored + the retention time
6. Cost items are tagged
    * Cost item tags comes from cloud resource tags and from provider services
    * Note that *Dimensions* can be seen conceptually as specific *tags* that have been promoted as first-class citizens in the model for cost reporting
    * The *ProviderTagSelector* field in cost allocation data enables a finer grained cost selection and allocation along additional axis (e.g. customer)
7. A cost allocation key can allocate cost both to a service and to a product
    * Service cost allocation and product cost allocation actually work in parallel
        * The test `test2` illustrates how these cost allocation flows work together
    * Service cost allocation basically propagates costs through cost allocation keys
    * The cost of a service is the sum of the costs of cloud resources it uses directly and of the cost shares of the other services it consumes
    * Contrary to this, only the following costs are assigned to products from each service
        * The costs of cloud resources it uses directly and
        * Any costs from consumed services that did not report their costs to products
    * This ensures that there is no double counting of costs at product level
    * Assuming that all cloud resources are properly tagged and that services eventually allocate all their costs to products, then the costs of all cloud resources must be equal to the cost of all products
        * Similarly, the costs of a product that exclusively uses a single service would be equal to the total cost of that service
8. On-demand costs and amortized costs are supported in parallel by the model
    * Reporting the two is useful to investigate whether cost variations come from reservation management or something else
    * Reporting the two is also useful for service owners and product managers alike to see the savings made thanks to the reservation purchases
    * Reservation savings = On-demand costs - amortized costs
9. Cycles in the cost allocation can be broken by providing a *service precedence list*
    * Example: A monitoring system *M* running on top of a container service *C* is also used by the container service itself
        * In this case, part of the costs of *M* should be assigned back to *C*
        * Since the costs of *C* are allocated to *M* (in part), this creates a loop
        * This cost allocation cycle *C* -> *M* -> *C* can be broken by specifying a precedence list *C,M*. In this case, *C* is allocated no cost from *M*
    * As another example, see `test5` 
    * The cost allocation could manage cycles in a more sophisticated way in the future
10. As a general rule, the names of all model objects (products, services, instances, tags, ...) are normalized to lower case, in order avoid low-high case mistakes

## Bittersweet ways for a service to allocate its cost

The standard way for a service to allocate cost to its consumers is to provide dynamic cost allocation data containing cost allocation keys
Three alternatives exist to this, and they should be used carefully:
1. Use specific configurable *consumer service and product tags*
    * While providing an easy way to dynamically allocate costs, it does not offer any means to track usage and thus provides no hint to consumers on what drives their costs (black box)
    * See section *Consumer service and product tags* for details
2. Use specific *cost allocation type* in cost allocation data
    * E.g. to allocate a cost share proportional to the amortized costs of the consumers
    * See section *Cost allocation types in cost allocation data* below for details
3. Use a static cost allocation file
    * Instead of generating and using accurate consumption data, a static approach (potentially updated at certain intervals) might be sufficient in some cases and in crawl phase

### Consumer service and product tags

Specific configurable tags can be used by a service to allocate its cost to consumer services and to products.
Consumer tags are convenient to get cost allocation keys generated automatically based on tagging.

Technically, for every *CostItem* having consumer tags, a new *ConsumerCostItem* is created with:
- *ProviderService* and *ProviderInstance*: the ones from the *CostItem*.
- *ConsumerService* and *ConsumerInstance*: the ones from the consumer tags.
- *Product*: the one from the product tag.
- *ProviderTagSelector*: an expression matching the consumer tags.
- *ProviderCostAllocationKey*: value 1.0.
Examples are available in the tests `test3` and `test4`.

### Cost allocation types in cost allocation data

The default value of *ProviderCostAllocationType* in cost allocation data is *'Key'*.
Two other types of cost allocation are supported:
1. *'CloudTagSelector'*
    * The consumer service instances are not explicitly specified in the cost allocation data
        * They are inferred as the ones consuming the cloud cost items whose tags match the *ProviderCostAllocationCloudTagSelector* expression
    * The cost allocation keys are set as the amortized costs of the matching cloud cost items
    * This type of cost allocation is convenient to allocate costs to consumer services that run directly on the cloud proportionally to their cloud costs
2. *'Cost'*
    * The cost is allocated to the consumer services proportionally to their amortized costs
    * Technically, amortized costs are globally allocated to service instances in a first time, while ignoring this type of cost allocation
    * The amortized costs resulting from this cost allocation are used in a second pass as cost allocation keys to perform the actual cost allocation
    * Although this type of cost allocation is convenient to avoid bothering about cost allocation keys, it can produce results that are hardly predictable and understandable, depending on the complexity of the global cost allocation graph

Examples of *'CloudTagSelector'* and *'Cost'* cost allocation types are available in the test `test3`.

In theory, an even more general type of cost allocation could be considered:
- *'ConsumerTagSelector'*
    * Cost would be allocated to service instances whose cost items match the *ProviderCostAllocationConsumerTagSelector* expression proportionally to their amortized costs
    * While being more generic, this type of cost allocation can be even less predictable
    * This type of cost allocation has not been required and thus not implemented yet

### Allocation of further amounts [experimental]

Further amounts (on top of cloud costs) like emitted CO2 and electricity power.

### Configuration

Python `configparser` is used to manage the configuration. Here are the configuration parameters with examples:

```
[General]

# The date format, which is used both in input cost allocation data and output allocated cost data
# The format uses Python datetime syntax
# Do not forget to escape the % character
DateFormat = %%Y-%%m-%%d.

# The name of the default service to use for cost allocation when the service tag is missing
DefaultService = x

# The dimensions
Dimensions = Component,Environment

# The number of provider meter columns in input cost allocation data and output allocated cost data
NumberOfProviderMeters = 2

# The number of product dimensions in input cost allocation data and output allocated cost data
NumberOfProductDimensions = 2

# The number of product meter columns in input cost allocation data and output allocated cost data
NumberOfProductMeters = 3

[TagKey]

# The tag keys for service and instance
# In case of list, first matching key is used
Service = service,svc
Instance = instance

# The tag keys for the configured dimensions
# In case of list, first matching key is used
Component = component,comp
Environment = environment

# The consumer tag keys for service, instance and the configured dimensions
# In case of list, first matching key is used
ConsumerService = consumer_service
ConsumerInstance = consumer_instance
ConsumerComponent = consumer_component
ConsumerEnvironment = consumer_environment

# List of values to be ignored for the consumer tag
ConsumerServiceIgnoredValue = n/a

# The product tag key
# In case of list, first matching key is used
Product = product

[AzureEaAmortizedCost]

# The service, instance, and dimensions to allocate Azure unused reservation cost
UnusedReservationService = finops
UnusedReservationInstance = reservation
UnusedReservationComponent = unused

[Cycles]

# The precedence list for breaking cost allocation cycles
# Here, the cycle a -> b -> d ->a will be broken to a -> b -> d (cost allocation d -> a is removed)
ServicePrecedenceList = a,b,c

# The maximum number of cycles to break, as a safe guard to avoid programming loops or
# unexpected long execution time
MaxBreaks = 10

[FurtherAmounts]

# Further amounts to allocate
Amounts = Scope1Co2,Scope2Co2,Scope3Co2,ElectricityPower

# Allocation keys for further amounts
AllocationKeys = ElectricityPowerAllocationKey

# The allocation keys to use for further amounts
AmountAllocationKeys = Scope1Co2:ProviderCostAllocationKey,Scope2Co2:ProviderCostAllocationKey,Scope3Co2:ProviderCostAllocationKey,ElectricityPower:ElectricityPowerAllocationKey
```

## Test

Run the following command in the repository root directory:

```
python -m unittest -v tests.test
```

## Usage

The code for a simple command line in `main.py` is a basic example to:
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

## TODO

- Cost readers for GCP and AWS.
- Split and dispatch of the provider meter values when CloudTagSelector is used.
- Support product dimension in cloud tags
- Unit test for further amount allocation
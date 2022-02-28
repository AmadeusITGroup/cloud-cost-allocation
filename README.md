# Cloud cost allocation

## General
Standard cloud provider and vendor cost management tools rely on two data sources, which are available in billing data:
- *Resource containers*, like *Projects* in *Google Cloud Platform*, or *Subscriptions* and *Resource Groups* in *Azure*. For example, the cost of a given Azure subscription can be allocated to a given organization or cost center. 
- *Tags*. For example, resources tagged with *cost_center:1234* are allocated to the *Cost Center 1234*.

Such cost allocation does not address *hierarchical service consumption*, where services are deployed and operated within the same company (case of *shared services* with multiple sharing levels): 

![](./hierarchical-service-consumption.svg)

Such consumption hierarchy has to be reflected in the cost allocation. Furthermore, the cost allocation of service should not be arbitrary, but based on usage: the more you use a service, the more you get cost allocated from it. This OpenSource code proposes a cost allocation model that supports any arbitrary consumption hierarchy and implements the FinOps Unit Economics approach for shared services.

## Definitions

## UML CLass Diagram

## Model principles

## Test

## Example

## Contributing 

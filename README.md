# QAOA for Dark Store location and inventory optimization

A quantum optimization system for **joint dark-store location, demand assignment, and inventory optimization** using **QUBO and QAOA**.

## About the Project

The **QAOA Dark Store Optimizer** identifies suitable store locations, assigns demand areas to stores, and determines inventory requirements while considering budget, storage capacity, and delivery-time constraints.

The logistics problem is formulated as a **QUBO (Quadratic Unconstrained Binary Optimization)** model and solved using **QAOA (Quantum Approximate Optimization Algorithm)**. The QAOA solution is compared with a classical **PuLP/CBC** optimization model for validation.

## How It Works

**Real/Public Data → Demand & Store Modeling → QUBO → QAOA → Solution → Validation → Classical Comparison**

## Key Features

- Dark-store location optimization
- Demand-area assignment
- Inventory allocation
- Budget and capacity constraints
- Delivery-time constraints
- QUBO formulation
- QAOA optimization using Qiskit
- Classical PuLP/CBC comparison
- Independent solution validation
- Real road-network travel times
- Interactive React dashboard

## Data Used

- **48** candidate store locations from OpenStreetMap
- **163** demand zones
- **25** public quick-commerce products
- **7,824** OSRM road-routing legs
- **1,150** demand records based on population-derived estimates

## Optimization Objective

The system maximizes:

**Served Margin − Store Opening Cost − Delivery/Rider Cost**

while satisfying budget, capacity, assignment, service, and demand constraints.

## QUBO and QAOA

The business problem is converted into a QUBO formulation using binary decision variables.

QAOA is then used to search for a high-quality solution using Qiskit and a classical parameter optimizer.

The result is evaluated using objective value, feasibility, constraint violations, runtime, and optimality gap.

## Classical Comparison

The QAOA solution is compared with **PuLP/CBC** as a classical optimization baseline.

Example validated result:

| Method | Objective |
|---|---:|
| QUBO Brute Force | ₹14,716.14 |
| PuLP/CBC | ₹14,716.14 |
| QAOA | ₹14,716.14 |

The QAOA solution matched the classical optimum in this experiment with a **0% optimality gap**.

## Technology Stack

**Python • Qiskit • QAOA • QUBO • FastAPI • React • Supabase PostgreSQL • OpenStreetMap • OSRM • PuLP/CBC**

## Project Workflow

```text
Public Data
    ↓
Data Processing
    ↓
Optimization Model
    ↓
QUBO Formulation
    ↓
QAOA
    ↓
Store + Demand + Inventory Solution
    ↓
Validation
    ↓
Classical Comparison
    ↓
Dashboard

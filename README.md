# CRUX-Inspired Fairness Testbed on FABRIC

This project implements a small testbed to study the fairness-utilization tradeoff in shared GPU clusters, inspired by the CRUX scheduler. It is designed to run on the FABRIC testbed.

## Overview

The system consists of:

- **Workers (Nodes A & B)**: Run GPU-intensive or communication-heavy jobs.
- **Scheduler (Node C)**: Receives metrics, calculates priorities based on GPU intensity and throughput degradation, and schedules network traffic.

## Project Structure

- `src/`: Source code for Worker and Scheduler.
- `scripts/`: Scripts for running experiments and provisioning FABRIC nodes.
- `.github/`: CI/CD workflows for simulation and deployment.

## Setup

### Prerequisites

- Python 3.9+
- FABRIC account and credentials (for deployment)

### Installation

```bash
pip install -r requirements.txt
```

## Running Locally (Simulation)

You can run a local simulation (using multiprocessing and loopback interface) to verify logic:

```bash
python scripts/run_experiment.py --mode simulation
```

## Running on FABRIC

1. Configure your FABRIC secrets in `fabric_rc`.
2. Provision nodes:
   ```bash
   python scripts/provision_fabric.py
   ```
3. Run the experiment:
   ```bash
   python scripts/run_experiment.py --mode fabric
   ```

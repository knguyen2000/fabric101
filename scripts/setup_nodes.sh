#!/bin/bash

# Update and Install Dependencies
sudo apt-get update
sudo apt-get install -y python3-pip python3-dev iproute2

# Install Python Libs
pip3 install torch numpy matplotlib

# Setup Traffic Control (Scheduler Node Only - but safe to run on all)
# We will apply specific rules in the experiment script or manually
# This just ensures tc is available (it usually is)
which tc

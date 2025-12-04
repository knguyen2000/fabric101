import subprocess
import time
import argparse
import sys
import os
import threading

def run_simulation():
    print("Starting Simulation...")
    
    # 1. Start Scheduler
    print("Launching Scheduler...")
    scheduler = subprocess.Popen([sys.executable, "src/scheduler.py", "--beta", "1.0"])
    time.sleep(2) # Wait for scheduler to start
    
    # 2. Start Workers
    # Job A: Compute heavy (large model), small comm
    print("Launching Worker A...")
    worker_a = subprocess.Popen([
        sys.executable, "src/worker.py",
        "--job_id", "A",
        "--model_size", "4096", # More compute
        "--grad_mb", "1",       # Less comm
        "--steps", "50"
    ])
    
    # Job B: Comm heavy (small model), large comm
    print("Launching Worker B...")
    worker_b = subprocess.Popen([
        sys.executable, "src/worker.py",
        "--job_id", "B",
        "--model_size", "128",  # Less compute
        "--grad_mb", "50",      # More comm
        "--steps", "50"
    ])
    
    # Wait for workers
    worker_a.wait()
    worker_b.wait()
    
    print("Workers finished.")
    scheduler.terminate()
    print("Experiment Complete.")

def run_fabric():
    print("FABRIC mode not yet implemented in this script. Use provision_fabric.py to setup nodes first.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["simulation", "fabric"], default="simulation")
    args = parser.parse_args()
    
    # Ensure we are in the root directory
    if not os.path.exists("src"):
        print("Error: Must run from project root.")
        sys.exit(1)

    if args.mode == "simulation":
        run_simulation()
    else:
        run_fabric()

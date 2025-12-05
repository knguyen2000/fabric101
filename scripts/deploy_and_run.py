import os
import json
from fabrictestbed_extensions.fablib.fablib import FablibManager as fablib_manager

# Configure FABRIC environment
fab_dir = os.path.expanduser('~/.fabric')
os.makedirs(fab_dir, exist_ok=True)

os.environ['FABRIC_TOKEN_LOCATION'] = os.path.join(fab_dir, 'id_token.json')
os.environ['FABRIC_BASTION_KEY_LOCATION'] = os.path.join(fab_dir, 'bastion_key')
os.environ['FABRIC_SLICE_PRIVATE_KEY_FILE'] = os.path.join(fab_dir, 'slice_key')
os.environ['FABRIC_SLICE_PUBLIC_KEY_FILE'] = os.path.join(fab_dir, 'slice_key.pub')

os.environ['FABRIC_LOG_LEVEL'] = os.environ.get('FABRIC_LOG_LEVEL', 'INFO')
os.environ['FABRIC_QUIET'] = 'True'

def deploy_and_run(slice_name="crux_testbed"):
    """
    Connect to existing FABRIC slice, deploy code, and run experiment.
    """
    fablib = fablib_manager()
    
    # Get existing slice
    try:
        slice = fablib.get_slice(name=slice_name)
        print(f"✓ Found existing slice: {slice_name}")
    except Exception as e:
        print(f"✗ Error: Slice '{slice_name}' not found!")
        print(f"  Please run the 'Provision FABRIC Infrastructure' workflow first.")
        raise e
    
    # Get nodes
    worker_a = slice.get_node('worker-a')
    worker_b = slice.get_node('worker-b')
    scheduler_c = slice.get_node('scheduler-c')
    
    print("✓ Found all nodes")
    
    # Upload code to nodes
    print("\n📦 Deploying code to nodes...")
    
    for node in [worker_a, worker_b, scheduler_c]:
        print(f"  → {node.get_name()}")
        
        # Upload source code
        node.upload_directory('src', 'crux_testbed/src')
        node.upload_directory('scripts', 'crux_testbed/scripts')
        
        # Install dependencies
        node.execute('sudo apt-get update && sudo apt-get install -y python3-pip iproute2')
        node.execute('pip3 install torch numpy matplotlib')
    
    print("✓ Code deployed to all nodes")
    
    # Configure bandwidth shaping on scheduler
    print("\n🌐 Configuring network bandwidth...")
    scheduler_c.execute('sudo tc qdisc del dev eth1 root || true')  # Clear existing
    scheduler_c.execute('sudo tc qdisc add dev eth1 root tbf rate 1gbit burst 32kbit latency 200ms')
    print("✓ Bandwidth shaping configured")
    
    # Run experiment
    print("\n🚀 Starting experiment...")
    
    # Start scheduler on node C
    print("  → Starting scheduler on scheduler-c...")
    scheduler_c.execute('cd crux_testbed && nohup python3 src/scheduler.py --beta 1.0 > scheduler.log 2>&1 &')
    
    # Give scheduler time to start
    import time
    time.sleep(3)
    
    # Start workers
    scheduler_ip = '192.168.10.12'  # From provisioning script
    
    print("  → Starting worker A...")
    worker_a.execute(f'cd crux_testbed && nohup python3 src/worker.py --job_id A --scheduler_host {scheduler_ip} --receiver_host {scheduler_ip} --model_size 4096 --grad_mb 1 --steps 50 > worker_a.log 2>&1 &')
    
    print("  → Starting worker B...")
    worker_b.execute(f'cd crux_testbed && nohup python3 src/worker.py --job_id B --scheduler_host {scheduler_ip} --receiver_host {scheduler_ip} --model_size 128 --grad_mb 50 --steps 50 > worker_b.log 2>&1 &')
    
    print("✓ Experiment started")
    
    # Wait for completion (adjust based on expected runtime)
    print("\n⏳ Waiting for experiment to complete (estimated: 60 seconds)...")
    time.sleep(60)
    
    # Collect results
    print("\n📥 Collecting results...")
    
    # Download log files (if they exist)
    try:
        worker_a.download_file('/home/ubuntu/crux_testbed/worker_a.log', 'worker_a.log')
    except Exception as e:
        print(f"  Warning: Could not download worker_a.log: {e}")
    
    try:
        worker_b.download_file('/home/ubuntu/crux_testbed/worker_b.log', 'worker_b.log')
    except Exception as e:
        print(f"  Warning: Could not download worker_b.log: {e}")
    
    try:
        scheduler_c.download_file('/home/ubuntu/crux_testbed/scheduler.log', 'scheduler.log')
    except Exception as e:
        print(f"  Warning: Could not download scheduler.log: {e}")
    
    print("✓ Results download attempted")
    
    # Save node info
    results = {
        "slice_name": slice_name,
        "nodes": {
            "worker-a": str(worker_a.get_management_ip()),
            "worker-b": str(worker_b.get_management_ip()),
            "scheduler-c": str(scheduler_c.get_management_ip())
        },
        "status": "completed"
    }
    
    with open("experiment_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print("\n✅ Experiment complete! Check the artifacts for logs and results.")

if __name__ == "__main__":
    deploy_and_run()

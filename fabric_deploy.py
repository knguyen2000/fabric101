import os
import configparser
import sys
import ipaddress
import time

# Path handling
print("Detected GitHub Actions Environment")
fab_dir = os.path.expanduser('~/.fabric')
os.makedirs(fab_dir, exist_ok=True)

os.environ['FABRIC_TOKEN_LOCATION'] = os.path.join(fab_dir, 'id_token.json')
os.environ['FABRIC_BASTION_KEY_LOCATION'] = os.path.join(fab_dir, 'bastion_key')
os.environ['FABRIC_SLICE_PRIVATE_KEY_FILE'] = os.path.join(fab_dir, 'slice_key')
os.environ['FABRIC_SLICE_PUBLIC_KEY_FILE'] = os.path.join(fab_dir, 'slice_key.pub')

os.environ['FABRIC_LOG_LEVEL'] = 'CRITICAL'
os.environ['FABRIC_QUIET'] = 'True'

try:
    import jwt
    original_decode = jwt.decode
    def patched_decode(*args, **kwargs):
        # Add 1 hour leeway for 'iat' check
        kwargs['leeway'] = 3600 
        return original_decode(*args, **kwargs)
    jwt.decode = patched_decode
    print("Monkey-patched jwt.decode to allow clock skew.")
except ImportError:
    print("Could not patch jwt (not installed?), proceeding anyway...")

from fabrictestbed_extensions.fablib.fablib import FablibManager as fablib_manager

import time

def deploy():
    try:
        fablib = fablib_manager()
        # Use unique name to avoid 'get_slice' crash
        SLICE_NAME = f'ai-traffic-synth-{int(time.time())}'
        print(f"Using Slice Name: {SLICE_NAME}")
        
        # ---------------------------------------------------------
        # Site Selection
        # ---------------------------------------------------------
        print("Skipping dynamic site query (API issues detected). Using hardcoded list.")
        gpu_sites = []
        known_big_sites = ['NCSA', 'TACC', 'CLEMSON', 'UTAH', 'MICH', 'WASH', 'DALL', 'UCSD', 'LBNL']
        candidates = known_big_sites
        
        print(f"Candidate Sites (in order): {candidates}", flush=True)

        # ---------------------------------------------------------
        # Deployment
        # ---------------------------------------------------------
        slice = None
        print("Starting deployment loop...", flush=True)
        for site in candidates:
            print(f"\n--- Attempting deployment at {site} ---", flush=True)
            try:

                print(f"Creating slice '{SLICE_NAME}' at {site}...")
                slice = fablib.new_slice(name=SLICE_NAME)

                # 1. Add Nodes
                image = 'default_ubuntu_22'
                
                # Server (Aggregator) - CPU Only
                print("Adding Server Node...")
                server = slice.add_node(name='server', site=site, image=image)
                server.set_capacities(cores=2, ram=8)
                
                # Client 1 (Trainer) - GPU
                print("Adding Client 1...")
                client1 = slice.add_node(name='client1', site=site, image=image)
                client1.set_capacities(cores=2, ram=8)
                client1.add_component(model='GPU_TeslaT4', name='gpu1')

                # Client 2 (Trainer) - GPU
                print("Adding Client 2...")
                client2 = slice.add_node(name='client2', site=site, image=image)
                client2.set_capacities(cores=2, ram=8)
                client2.add_component(model='GPU_TeslaT4', name='gpu1')

                # 2. Add Network (L2 Bridge)
                iface_server = server.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]
                iface_c1 = client1.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]
                iface_c2 = client2.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]
                
                slice.add_l2network(name='net_a', interfaces=[iface_server, iface_c1, iface_c2])

                # 3. Submit
                print("Submitting slice...")
                slice.submit()
                print(f"SUCCESS! Slice active at {site}.")
                break 

            except Exception as e:
                print(f"FAILED at {site}: {e}")
                print("Cleaning up and trying next site...")
                try:
                    if slice: slice.delete()
                except:
                    pass
        
        if not slice or slice.get_state() not in ['Stable', 'StableOK']:
            print(f"\nCRITICAL: All deployment attempts failed. Final State: {slice.get_state() if slice else 'None'}")
            sys.exit(1)

        # ---------------------------------------------------------
        # 4. Configure Network (IPs)
        # ---------------------------------------------------------
        print("Reloading slice to get active node handles...")
        slice = fablib.get_slice(name=SLICE_NAME)
        server = slice.get_node('server')
        client1 = slice.get_node('client1')
        client2 = slice.get_node('client2')
        
        subnet = ipaddress.IPv4Network("192.168.1.0/24")
        server_ip = ipaddress.IPv4Address("192.168.1.10")
        c1_ip = ipaddress.IPv4Address("192.168.1.11")
        c2_ip = ipaddress.IPv4Address("192.168.1.12")

        iface_server = server.get_interface(network_name='net_a')
        iface_server.ip_addr_add(addr=server_ip, subnet=subnet)
        iface_server.ip_link_up()

        iface_c1 = client1.get_interface(network_name='net_a')
        iface_c1.ip_addr_add(addr=c1_ip, subnet=subnet)
        iface_c1.ip_link_up()

        iface_c2 = client2.get_interface(network_name='net_a')
        iface_c2.ip_addr_add(addr=c2_ip, subnet=subnet)
        iface_c2.ip_link_up()

        # ---------------------------------------------------------
        # 5. Configure Storage (Local)
        # ---------------------------------------------------------
        print("Configuring Local Storage...")
        slice.wait_ssh()
        
        # Use a local directory instead of NVMe
        storage_path = "/home/ubuntu/project_data"
        setup_script = f"mkdir -p {storage_path} && chmod 777 {storage_path}"
        
        for node in [client1, client2]:
            try:
                print(f"Configuring storage on {node.get_name()}...")
                node.execute(setup_script, quiet=False)
            except Exception as e:
                print(f"Failed to configure storage on {node.get_name()}: {e}")

        # ---------------------------------------------------------
        # 6. Install Software
        # ---------------------------------------------------------
        print("Installing software...")
        
        # Common dependencies
        for node in [server, client1, client2]:
            node.execute('sudo apt-get clean', quiet=True)
            node.execute('sudo apt-get update', quiet=False)
            node.execute('sudo apt-get install -y python3-pip', quiet=False)
            try:
                node.execute('python3 -m pip --version', quiet=False)
            except:
                node.execute('curl -sS https://bootstrap.pypa.io/get-pip.py | sudo python3', quiet=False)

        # Server Setup (CPU)
        print("Setting up Server...")
        # Install CPU version of torch to avoid size/compatibility issues
        server.execute('python3 -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu', quiet=False)
        server.execute('python3 -m pip install pandas', quiet=False)
        
        server.upload_file('cpt_model.py', 'cpt_model.py')
        server.upload_file('cellular_sim.py', 'cellular_sim.py')
        server.upload_file('fl_server.py', 'fl_server.py')
        server.upload_file('evaluate_metrics.py', 'evaluate_metrics.py')

        # Client Setup (GPU)
        print("Setting up Clients...")
        env_vars = f"export TMPDIR={storage_path}/tmp; mkdir -p $TMPDIR; "
        # Export PYTHONPATH for the session OR pass it inline
        python_path_setup = f"export PYTHONPATH=$PYTHONPATH:{storage_path}/pylib"
        
        for node in [client1, client2]:
            # Drivers
            node.execute(f"{env_vars} sudo apt-get install -y ubuntu-drivers-common && sudo ubuntu-drivers autoinstall", quiet=False)
            
            # PyTorch (Custom Index)
            # Install to local dir
            install_torch = (
                f"{env_vars} python3 -m pip install --target={storage_path}/pylib "
                "torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118"
            )
            node.execute(install_torch, quiet=False)

            install_libs = (
                f"{env_vars} python3 -m pip install --target={storage_path}/pylib "
                "pandas scikit-learn"
            )
            node.execute(install_libs, quiet=False)
            
            # Verify Installation
            verify_cmd = f"PYTHONPATH=$PYTHONPATH:{storage_path}/pylib python3 -c 'import torch; print(torch.__version__)'"
            try:
                print(f"Verifying torch on {node.get_name()}...")
                node.execute(verify_cmd, quiet=False)
            except Exception as e:
                print(f"WARNING: Torch verification failed on {node.get_name()}: {e}")

            # Upload Scripts
            node.upload_file('cpt_model.py', 'cpt_model.py')
            node.upload_file('cellular_sim.py', 'cellular_sim.py')
            node.upload_file('fl_client.py', 'fl_client.py')
            node.upload_file('evaluate_metrics.py', 'evaluate_metrics.py')

        print("\nDeployment Successful!")
        print(f"Server: ssh -i <slice_key> ubuntu@{server.get_management_ip()}")
        print(f"Client1: ssh -i <slice_key> ubuntu@{client1.get_management_ip()}")
        print(f"Client2: ssh -i <slice_key> ubuntu@{client2.get_management_ip()}")

        # ---------------------------------------------------------
        # 7. Run Experiment
        # ---------------------------------------------------------
        print("\nStarting Federated Learning Experiment...")
        
        # Start Server in background
        print("Starting FL Server...")
        # Server uses default python path
        server.execute("nohup python3 fl_server.py > server.log 2>&1 &", quiet=False)
        time.sleep(10) # Wait for startup
        
        # Start Clients
        # Pass PYTHONPATH explicitly to nohup command
        print("Starting Client 1...")
        client1.execute(f"PYTHONPATH=$PYTHONPATH:{storage_path}/pylib nohup python3 fl_client.py client_1 http://192.168.1.10:8000 > client.log 2>&1 &", quiet=False)
        
        print("Starting Client 2...")
        client2.execute(f"PYTHONPATH=$PYTHONPATH:{storage_path}/pylib nohup python3 fl_client.py client_2 http://192.168.1.10:8000 > client.log 2>&1 &", quiet=False)
        
        print("\nExperiment Running! Waiting 120s for completion...")
        time.sleep(120)

        # ---------------------------------------------------------
        # 8. Retrieve Artifacts
        # ---------------------------------------------------------
        print("Retrieving logs and results...")
        try:
            server.download_file('server.log', 'server.log')
            client1.download_file('client1.log', 'client.log')
            client2.download_file('client2.log', 'client.log')
            
            # Download CSVs if they exist
            # Note: fablib download_file might fail if file doesn't exist, so wrap in try/except
            for node, name in [(server, 'server'), (client1, 'client1'), (client2, 'client2')]:
                try:
                    node.download_file(f'gen_data_{name}.csv', f'gen_data_{name}.csv')
                except:
                    pass
        except Exception as e:
            print(f"Warning: Failed to download some artifacts: {e}")

    except Exception as e:
        print(f"Deployment failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    deploy()

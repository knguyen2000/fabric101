import os
import time
import json
from ipaddress import IPv4Network
from fabrictestbed_extensions.fablib.fablib import FablibManager as fablib_manager

fab_dir = os.path.expanduser('~/.fabric')
os.makedirs(fab_dir, exist_ok=True)

os.environ['FABRIC_TOKEN_LOCATION'] = os.path.join(fab_dir, 'id_token.json')
os.environ['FABRIC_BASTION_KEY_LOCATION'] = os.path.join(fab_dir, 'bastion_key')
os.environ['FABRIC_SLICE_PRIVATE_KEY_FILE'] = os.path.join(fab_dir, 'slice_key')
os.environ['FABRIC_SLICE_PUBLIC_KEY_FILE'] = os.path.join(fab_dir, 'slice_key.pub')

os.environ['FABRIC_LOG_LEVEL'] = os.environ.get('FABRIC_LOG_LEVEL', 'CRITICAL')
os.environ['FABRIC_QUIET'] = 'True'

def provision_slice(slice_name="crux_testbed"):
    fablib = fablib_manager()
    
    try:
        slice = fablib.get_slice(name=slice_name)
        print(f"Slice {slice_name} already exists. Deleting...")
        slice.delete()
    except:
        pass

    print(f"Creating slice {slice_name}...")
    slice = fablib.new_slice(name=slice_name)

    # Constraints
    CORES = 2
    RAM = 10
    DISK = 10  # Max allowed without VM.NoLimitDisk tag
    IMAGE = 'default_ubuntu_20'
    SITE = 'SALT'  # Force all nodes to same site (L2 networks limited to 2 sites)

    # 1. Add Nodes
    # Worker A
    print("Adding Worker A...")
    worker_a = slice.add_node(name='worker-a', site=SITE, cores=CORES, ram=RAM, disk=DISK, image=IMAGE)
    worker_a.add_component(model='GPU_TeslaT4', name='gpu1')
    iface_a = worker_a.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]

    # Worker B
    print("Adding Worker B...")
    worker_b = slice.add_node(name='worker-b', site=SITE, cores=CORES, ram=RAM, disk=DISK, image=IMAGE)
    worker_b.add_component(model='GPU_TeslaT4', name='gpu1')
    iface_b = worker_b.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]

    # Scheduler C
    print("Adding Scheduler C...")
    scheduler_c = slice.add_node(name='scheduler-c', site=SITE, cores=CORES, ram=RAM, disk=DISK, image=IMAGE)
    iface_c = scheduler_c.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]

    # 2. L2 Network
    print("Creating L2 Network...")
    net = slice.add_l2network(name='crux_net', interfaces=[iface_a, iface_b, iface_c])

    # 3. Submit
    print("Submitting slice request...")
    slice.submit()

    # 4. Configure Network
    print("Configuring Network...")
    
    # IPs
    # Worker A: 192.168.10.10
    # Worker B: 192.168.10.11
    # Scheduler C: 192.168.10.12
    
    iface_a = slice.get_node('worker-a').get_interface(network_name='crux_net')
    iface_a.ip_addr_add(addr='192.168.10.10', subnet=IPv4Network('192.168.10.0/24'))
    iface_a.ip_link_up()

    iface_b = slice.get_node('worker-b').get_interface(network_name='crux_net')
    iface_b.ip_addr_add(addr='192.168.10.11', subnet=IPv4Network('192.168.10.0/24'))
    iface_b.ip_link_up()

    iface_c = slice.get_node('scheduler-c').get_interface(network_name='crux_net')
    iface_c.ip_addr_add(addr='192.168.10.12', subnet=IPv4Network('192.168.10.0/24'))
    iface_c.ip_link_up()

    print("Slice provisioning complete.")
    
    # Save details
    details = {
        "worker-a": slice.get_node('worker-a').get_management_ip(),
        "worker-b": slice.get_node('worker-b').get_management_ip(),
        "scheduler-c": slice.get_node('scheduler-c').get_management_ip()
    }
    with open("slice_details.json", "w") as f:
        json.dump(details, f)

if __name__ == "__main__":
    provision_slice()

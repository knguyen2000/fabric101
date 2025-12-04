import time
import socket
import argparse
import torch
import torch.nn as nn
import numpy as np
from utils import *

class SimpleModel(nn.Module):
    def __init__(self, size):
        super().__init__()
        self.fc = nn.Linear(size, size)

    def forward(self, x):
        return self.fc(x)

def run_worker(job_id, scheduler_host, receiver_host, model_size, grad_mb, steps):
    print(f"Worker {job_id} starting...")
    
    # Connect to Scheduler (Control)
    ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while True:
        try:
            ctrl_sock.connect((scheduler_host, SCHEDULER_CONTROL_PORT))
            break
        except ConnectionRefusedError:
            time.sleep(1)
            print(f"Worker {job_id} waiting for scheduler...")

    # Connect to Receiver (Data) - simulated by connecting to scheduler's data port for now or a separate receiver
    # For this implementation, we'll assume the receiver is also the scheduler node but on a different port (or just a sink)
    # In the plan, we said "Receiver (data)". Let's assume the scheduler also acts as the data sink for simplicity, 
    # or we can spawn a separate receiver process. 
    # Let's use a separate DATA port on the Scheduler host for the data sink.
    data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while True:
        try:
            data_sock.connect((receiver_host, WORKER_DATA_PORT))
            break
        except ConnectionRefusedError:
            time.sleep(1)
    
    # Setup Model
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SimpleModel(model_size).to(device)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
    input_data = torch.randn(64, model_size).to(device)

    # Payload
    payload_size = int(grad_mb * 1024 * 1024)
    payload = b'a' * payload_size

    for step in range(steps):
        # 1. Compute
        start_comp = time.time()
        optimizer.zero_grad()
        out = model(input_data)
        loss = out.sum()
        loss.backward()
        optimizer.step()
        if device == "cuda":
            torch.cuda.synchronize()
        compute_time = time.time() - start_comp

        # 2. Report Metrics
        # We need to estimate throughput. For the first step, we don't know.
        # Let's send the compute time and last step's comm time (or 0).
        
        # Protocol: Send metrics -> Wait for ALLOW -> Send Data -> Measure Comm Time
        
        # We need to send a request to send.
        req = {
            "job_id": job_id,
            "compute_time": compute_time,
            "payload_size": payload_size
        }
        send_json(ctrl_sock, req)

        # 3. Wait for Schedule
        while True:
            resp = recv_json(ctrl_sock)
            if resp and resp.get("command") == "ALLOW_SEND":
                break
            # If WAIT, we just wait for the next message. 
            # The scheduler might send WAIT then ALLOW later? 
            # Or we poll? The plan said "Wait for ALLOW". 
            # Let's assume the scheduler sends ALLOW when it's our turn.
        
        # 4. Communicate
        start_comm = time.time()
        send_bulk(data_sock, payload)
        # Wait for ack from receiver? TCP guarantees delivery, but app-level ack is good for timing.
        # For simplicity, we count sendall time.
        comm_time = time.time() - start_comm
        
        # Report completion to scheduler? 
        # The scheduler needs to know we finished to schedule others.
        # We can send a "FINISHED" message on control socket.
        send_json(ctrl_sock, {"job_id": job_id, "status": "FINISHED", "comm_time": comm_time})

        print(f"Job {job_id}: Step {step}, Comp {compute_time:.4f}s, Comm {comm_time:.4f}s")
        time.sleep(0.01) # Small sleep to prevent tight loops

    ctrl_sock.close()
    data_sock.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--job_id", type=str, required=True)
    parser.add_argument("--scheduler_host", type=str, default="localhost")
    parser.add_argument("--receiver_host", type=str, default="localhost")
    parser.add_argument("--model_size", type=int, default=1024)
    parser.add_argument("--grad_mb", type=float, default=10)
    parser.add_argument("--steps", type=int, default=100)
    args = parser.parse_args()

    run_worker(args.job_id, args.scheduler_host, args.receiver_host, args.model_size, args.grad_mb, args.steps)

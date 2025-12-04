import socket
import threading
import time
import argparse
import select
from utils import *

class Scheduler:
    def __init__(self, beta):
        self.beta = beta
        self.job_states = {} # {job_id: {iso_thr, curr_thr, I, D, P, socket}}
        self.lock = threading.Lock()
        self.active_sender = None
        self.running = True

    def handle_control_client(self, sock):
        while self.running:
            msg = recv_json(sock)
            if not msg:
                break
            
            job_id = msg.get("job_id")
            
            with self.lock:
                if job_id not in self.job_states:
                    self.job_states[job_id] = {
                        "iso_thr": 1.0, # Placeholder, needs calibration phase
                        "curr_thr": 0.0,
                        "I": 0.0,
                        "D": 0.0,
                        "P": 0.0,
                        "sock": sock,
                        "waiting": False
                    }
                
                state = self.job_states[job_id]
                
                if "status" in msg and msg["status"] == "FINISHED":
                    # Job finished sending
                    comm_time = msg["comm_time"]
                    # Update throughput (simplified)
                    # throughput = payload / (comp + comm)
                    # We need to track total time.
                    self.active_sender = None
                    self.schedule_next()
                
                elif "compute_time" in msg:
                    # Job wants to send
                    state["waiting"] = True
                    state["last_compute"] = msg["compute_time"]
                    state["last_payload"] = msg["payload_size"]
                    
                    # Update Priority
                    # I = compute / comm (use last comm time or small epsilon)
                    last_comm = state.get("last_comm", 1e-6)
                    state["I"] = msg["compute_time"] / max(last_comm, 1e-6)
                    
                    # D = (iso - curr) / iso
                    # For now, let's just use I for P if beta=1
                    state["P"] = self.beta * state["I"] # + (1-beta)*D
                    
                    self.schedule_next()

    def schedule_next(self):
        if self.active_sender:
            return

        # Find waiting jobs
        candidates = [jid for jid, s in self.job_states.items() if s["waiting"]]
        if not candidates:
            return

        # Pick highest P
        winner_id = max(candidates, key=lambda jid: self.job_states[jid]["P"])
        
        self.active_sender = winner_id
        self.job_states[winner_id]["waiting"] = False
        
        # Send ALLOW
        send_json(self.job_states[winner_id]["sock"], {"command": "ALLOW_SEND"})

    def start_control_server(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((SCHEDULER_HOST, SCHEDULER_CONTROL_PORT))
        s.listen(5)
        print(f"Scheduler Control listening on {SCHEDULER_CONTROL_PORT}")
        
        while self.running:
            conn, addr = s.accept()
            t = threading.Thread(target=self.handle_control_client, args=(conn,))
            t.daemon = True
            t.start()

    def start_data_sink(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((SCHEDULER_HOST, WORKER_DATA_PORT))
        s.listen(5)
        print(f"Data Sink listening on {WORKER_DATA_PORT}")
        
        while self.running:
            conn, addr = s.accept()
            # Just drain data
            t = threading.Thread(target=self.drain_data, args=(conn,))
            t.daemon = True
            t.start()

    def drain_data(self, sock):
        while self.running:
            data = recv_bulk(sock)
            if not data:
                break
            # Data received

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--beta", type=float, default=1.0)
    args = parser.parse_args()

    sched = Scheduler(args.beta)
    
    t_ctrl = threading.Thread(target=sched.start_control_server)
    t_data = threading.Thread(target=sched.start_data_sink)
    
    t_ctrl.start()
    t_data.start()
    
    t_ctrl.join()
    t_data.join()

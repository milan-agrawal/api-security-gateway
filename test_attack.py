import requests
import time
import threading
from colorama import Fore, Style, init

init(autoreset=True)

GATEWAY_URL = "http://127.0.0.1:8000/api/data"

# Define TWO different valid keys (from your main.py VALID_API_KEYS list)
BOB_KEY = "secret123"
ALICE_KEY = "client-demo-key"

def simulate_user(name, api_key, request_count, delay_between_requests, color):
    print(f"{color}--- {name} STARTED simulation ({request_count} requests) ---")
    headers = {"X-API-KEY": api_key}
    
    for i in range(1, request_count + 1):
        try:
            start = time.time()
            response = requests.get(GATEWAY_URL, headers=headers)
            latency = int((time.time() - start) * 1000)
            status = response.status_code
            
            if status == 200:
                msg = f"Request {i}: ALLOWED ({latency}ms)"
            elif status == 429:
                msg = f"Request {i}: BLOCKED (Rate Limit)"
            else:
                msg = f"Request {i}: ERROR {status}"
                
            print(f"{color}[{name}] {msg}")
            
        except Exception as e:
            print(f"{color}[{name}] Connection Error: {e}")
            
        time.sleep(delay_between_requests)

if __name__ == "__main__":
    print("Starting API Security Gateway Test (Separate Keys)...\n")
    
    # Bob uses 'secret123' and spams 20 requests
    bob_thread = threading.Thread(
        target=simulate_user, 
        args=("Bob (Hacker)", BOB_KEY, 20, 0.01, Fore.RED)
    )
    
    # Alice uses 'client-demo-key' and goes slowly
    alice_thread = threading.Thread(
        target=simulate_user, 
        args=("Alice (Normal)", ALICE_KEY, 5, 1.2, Fore.GREEN)
    )
    
    bob_thread.start()
    alice_thread.start()
    
    bob_thread.join()
    alice_thread.join()
    print("\nTest Finished.")
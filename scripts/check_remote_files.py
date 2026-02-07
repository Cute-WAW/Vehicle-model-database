import paramiko
import os

SERVER_IP = "112.124.71.198"
USERNAME = "root"
PASSWORD = "caili811229CAILI$" # Using the correct password identified earlier
REMOTE_PROJECT_PATH = "/root/car_price_predictor"

def check_remote_files():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"Connecting to {SERVER_IP}...")
        client.connect(SERVER_IP, username=USERNAME, password=PASSWORD)
        print("Connected.")
        
        # 1. Check Root Directory
        print(f"\nChecking directory: {REMOTE_PROJECT_PATH}")
        stdin, stdout, stderr = client.exec_command(f"ls -F {REMOTE_PROJECT_PATH}")
        files = stdout.read().decode().strip().split('\n')
        
        expected_files = ['src/', 'nginx/', 'docker-compose.aliyun.yml', 'requirements.txt', 'Dockerfile']
        missing = []
        
        if not files or files == ['']:
            print("Directory is empty or does not exist!")
            return

        print("Files found:")
        for f in files:
            print(f"  - {f}")
            
        for exp in expected_files:
            if exp not in files:
                missing.append(exp)
        
        if missing:
            print(f"\n[WARNING] Missing expected files: {missing}")
        else:
            print("\n[SUCCESS] All key root files are present.")

        # 2. Check Source Code (random check)
        print("\nChecking src directory...")
        stdin, stdout, stderr = client.exec_command(f"ls -F {REMOTE_PROJECT_PATH}/src")
        src_files = stdout.read().decode().strip()
        print(f"src contents:\n{src_files}")
        
        if "web_predictor_debug_step5.py" in src_files:
            print("  -> web_predictor_debug_step5.py found.")
        else:
            print("  -> [ERROR] web_predictor_debug_step5.py NOT found.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    check_remote_files()

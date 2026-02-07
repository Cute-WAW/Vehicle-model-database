import paramiko
import sys
import os
import time
from pathlib import Path

# Configuration
LOCAL_PROJECT_ROOT = r"d:\BaiduNetdiskDownload\车型库映射\车型库映射"
REMOTE_DIR = "/root/car_price_predictor"
DOCKER_IMAGE_NAME = "car-price-predictor"
DOCKER_CONTAINER_NAME = "car-price-predictor-v2" # v2 to distinguish from potential old ones
PORT = 8087 # Safe port

def create_ssh_client(hostname, username, password):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname, username=username, password=password)
    return client

def run_command(client, command, print_output=True):
    print(f"Executing: {command}")
    stdin, stdout, stderr = client.exec_command(command)
    exit_status = stdout.channel.recv_exit_status()
    
    out = stdout.read().decode('utf-8', errors='ignore').strip()
    err = stderr.read().decode('utf-8', errors='ignore').strip()
    
    if print_output:
        if out: print(out)
        if err: print(f"STDERR: {err}")
        
    return exit_status, out, err

def upload_files(sftp, local_path, remote_path):
    local_path = Path(local_path)
    remote_path = Path(remote_path).as_posix() # Ensure posix path for remote linux
    
    for item in local_path.rglob('*'):
        if item.is_file():
            # Skip some folders/files
            if any(part.startswith('.') for part in item.parts) or \
               '__pycache__' in item.parts or \
               'venv' in item.parts or \
               item.name.endswith('.pyc'):
                continue
                
            relative_path = item.relative_to(local_path)
            remote_file_path = f"{remote_path}/{relative_path.as_posix()}"
            remote_dir = os.path.dirname(remote_file_path)
            
            # Create remote directory if not exists (simple implementation, might be slow for deep trees)
            try:
                sftp.stat(remote_dir)
            except FileNotFoundError:
                # Recursively create dirs
                dirs_to_create = []
                current_dir = remote_dir
                while True:
                    try:
                        sftp.stat(current_dir)
                        break
                    except FileNotFoundError:
                        dirs_to_create.append(current_dir)
                        current_dir = os.path.dirname(current_dir)
                for d in reversed(dirs_to_create):
                    sftp.mkdir(d)
            
            print(f"Uploading {relative_path}...")
            sftp.put(str(item), remote_file_path)

def deploy(hostname, username, password):
    client = None
    try:
        print(f"Connecting to {hostname}...")
        client = create_ssh_client(hostname, username, password)
        sftp = client.open_sftp()
        
        # 1. Check Memory before starting
        print("\n--- Checking Initial Memory ---")
        _, mem_info, _ = run_command(client, "free -m")
        
        # 2. Create Remote Directory
        print(f"\n--- Creating Remote Directory: {REMOTE_DIR} ---")
        run_command(client, f"mkdir -p {REMOTE_DIR}")
        
        # 3. Upload Files (Simplified: Uploading essential files manually to avoid transferring huge venv/cache)
        print("\n--- Uploading Files ---")
        # Upload requirements.txt
        sftp.put(os.path.join(LOCAL_PROJECT_ROOT, "requirements.txt"), f"{REMOTE_DIR}/requirements.txt")
        # Upload Dockerfile
        sftp.put(os.path.join(LOCAL_PROJECT_ROOT, "Dockerfile"), f"{REMOTE_DIR}/Dockerfile")
        # Upload .env
        sftp.put(os.path.join(LOCAL_PROJECT_ROOT, ".env"), f"{REMOTE_DIR}/.env")
        
        # Upload src directory
        upload_files(sftp, os.path.join(LOCAL_PROJECT_ROOT, "src"), f"{REMOTE_DIR}/src")
        # Upload index directory
        upload_files(sftp, os.path.join(LOCAL_PROJECT_ROOT, "index"), f"{REMOTE_DIR}/index")
        # Upload price_model directory (only essential models if possible, but here we upload all as they are small)
        upload_files(sftp, os.path.join(LOCAL_PROJECT_ROOT, "price_model"), f"{REMOTE_DIR}/price_model")
        # Upload config directory
        upload_files(sftp, os.path.join(LOCAL_PROJECT_ROOT, "config"), f"{REMOTE_DIR}/config")
        
        # Create output directory
        run_command(client, f"mkdir -p {REMOTE_DIR}/output")
        # Upload merged_residual_value_data.csv if exists
        csv_path = os.path.join(LOCAL_PROJECT_ROOT, "output", "merged_residual_value_data.csv")
        if os.path.exists(csv_path):
            print("Uploading merged_residual_value_data.csv...")
            sftp.put(csv_path, f"{REMOTE_DIR}/output/merged_residual_value_data.csv")

        # 4. Build Docker Image
        print("\n--- Building Docker Image ---")
        build_cmd = f"cd {REMOTE_DIR} && docker build -t {DOCKER_IMAGE_NAME} ."
        status, _, _ = run_command(client, build_cmd)
        if status != 0:
            raise Exception("Docker build failed")

        # 5. Stop and Remove Old Container (if exists)
        print(f"\n--- Stopping Old Container {DOCKER_CONTAINER_NAME} (if any) ---")
        run_command(client, f"docker stop {DOCKER_CONTAINER_NAME}", print_output=False)
        run_command(client, f"docker rm {DOCKER_CONTAINER_NAME}", print_output=False)

        # 6. Start New Container
        print(f"\n--- Starting New Container on Port {PORT} ---")
        # Use --memory-swap to limit memory usage if needed, here we just monitor
        # We mount output to persist data
        run_cmd = f"docker run -d -p {PORT}:8087 \
            -v {REMOTE_DIR}/output:/app/output \
            -v {REMOTE_DIR}/users.db:/app/users.db \
            --env-file {REMOTE_DIR}/.env \
            --name {DOCKER_CONTAINER_NAME} \
            --restart unless-stopped \
            --memory=600m \
            {DOCKER_IMAGE_NAME}"
            
        status, out, err = run_command(client, run_cmd)
        if status != 0:
             raise Exception(f"Docker run failed: {err}")
        
        print("Container started successfully.")
        
        # 7. Post-Deployment Check
        print("\n--- Post-Deployment Checks ---")
        time.sleep(5) # Wait for startup
        run_command(client, f"docker ps | grep {DOCKER_CONTAINER_NAME}")
        run_command(client, "free -m")
        
        print(f"\nDeployment Complete! Access at http://{hostname}:{PORT}")

    except Exception as e:
        print(f"\nDeployment Failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if client: client.close()

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python deploy_to_server.py <host> <user> <password>")
        sys.exit(1)
        
    host = sys.argv[1]
    user = sys.argv[2]
    pwd = sys.argv[3]
    
    deploy(host, user, pwd)

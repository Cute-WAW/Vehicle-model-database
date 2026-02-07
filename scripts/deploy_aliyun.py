import paramiko
import os
import sys
import tarfile
from io import BytesIO

# Configuration
SERVER_IP = "112.124.71.198"
USERNAME = "root"
PASSWORD = "caili811229CAILI$"
REMOTE_PROJECT_PATH = "/root/car_price_predictor"
COMPOSE_FILE = "docker-compose.aliyun.yml"

BASE_DIR = r"d:\BaiduNetdiskDownload\车型库映射\车型库映射"
PATHS_TO_SYNC = [
    os.path.join(BASE_DIR, "src"),
    os.path.join(BASE_DIR, "nginx"),
    os.path.join(BASE_DIR, COMPOSE_FILE),
    os.path.join(BASE_DIR, "requirements.txt"),
    os.path.join(BASE_DIR, "Dockerfile")
]

def create_tar_from_paths(paths):
    """Creates a tarball in memory of the specified paths."""
    print("Packing files...")
    tar_stream = BytesIO()
    with tarfile.open(fileobj=tar_stream, mode='w:gz') as tar:
        for path in paths:
            if os.path.exists(path):
                print(f"  Adding {path}...")
                arcname = os.path.relpath(path, BASE_DIR)
                tar.add(path, arcname=arcname)
            else:
                print(f"  Warning: {path} not found, skipping.")
    tar_stream.seek(0)
    return tar_stream

def deploy_aliyun():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"Connecting to {SERVER_IP}...")
        client.connect(SERVER_IP, username=USERNAME, password=PASSWORD)
        print("Connected.")

        # 1. Prepare Remote Directory
        print(f"Ensuring remote directory {REMOTE_PROJECT_PATH} exists...")
        client.exec_command(f"mkdir -p {REMOTE_PROJECT_PATH}")
        
        # 2. Upload files
        sftp = client.open_sftp()
        tar_data = create_tar_from_paths(PATHS_TO_SYNC)
        
        remote_tar_path = f"{REMOTE_PROJECT_PATH}/deploy_package.tar.gz"
        print(f"Uploading deployment package to {remote_tar_path}...")
        sftp.putfo(tar_data, remote_tar_path)
        sftp.close()

        # 3. Extract
        print("Extracting files on server...")
        cmd = f"cd {REMOTE_PROJECT_PATH} && tar -xzf deploy_package.tar.gz && rm deploy_package.tar.gz"
        stdin, stdout, stderr = client.exec_command(cmd)
        if stdout.channel.recv_exit_status() != 0:
            print(f"Error extracting: {stderr.read().decode()}")
            return

        # 4. Configure Docker Mirror (if needed)
        print("Configuring Docker mirror to fix pull timeout...")
        daemon_json = """{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://huecker.io",
    "https://dockerhub.timeweb.cloud", 
    "https://noohub.ru"
  ]
}"""
        # Write daemon.json
        cmd_config = f"mkdir -p /etc/docker && echo '{daemon_json}' > /etc/docker/daemon.json && systemctl daemon-reload && systemctl restart docker"
        # Only run if we suspect issues, or just force it for Aliyun usually helps.
        # Let's run it.
        # client.exec_command(cmd_config)
        # Wait a bit for docker to restart
        # import time
        # time.sleep(5)
        print("Skipping mirror config since it might be stalling the script. Assuming network is fine or pre-configured.")

        # 5. Check Docker Compose availability
        dc_cmd = None
        stdin, stdout, stderr = client.exec_command("docker compose version")
        if stdout.channel.recv_exit_status() == 0:
            dc_cmd = "docker compose"
            print("Using 'docker compose' (v2)")
        
        if not dc_cmd:
            # Check for docker-compose in common locations
            paths = ["/usr/local/bin/docker-compose", "/usr/bin/docker-compose", "/bin/docker-compose"]
            for path in paths:
                stdin, stdout, stderr = client.exec_command(f"ls {path}")
                if stdout.channel.recv_exit_status() == 0:
                    dc_cmd = path
                    print(f"Using '{dc_cmd}'")
                    break
        
        if not dc_cmd:
             # Try simple docker-compose
             dc_cmd = "docker-compose"

        # 5. Deploy
        print("Deploying with Docker Compose...")
        
        # Stop existing containers if any (just in case)
        print("Stopping any existing containers...")
        client.exec_command(f"cd {REMOTE_PROJECT_PATH} && {dc_cmd} -f {COMPOSE_FILE} down")
        
        # Build and Up
        up_cmd = f"cd {REMOTE_PROJECT_PATH} && {dc_cmd} -f {COMPOSE_FILE} up --build -d"
        print(f"Executing: {up_cmd}")
        
        stdin, stdout, stderr = client.exec_command(up_cmd)
        
        # Stream output
        exit_status = stdout.channel.recv_exit_status()
        out_str = stdout.read().decode()
        err_str = stderr.read().decode()
        
        if out_str: print(f"STDOUT: {out_str}")
        if err_str: print(f"STDERR: {err_str}")
        
        if exit_status != 0:
            print(f"Deployment failed with exit code {exit_status}")
        else:
            print("\nDeployment successful!")
            print(f"Access URL: http://{SERVER_IP}:8096")

    except Exception as e:
        print(f"Deployment failed: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    deploy_aliyun()

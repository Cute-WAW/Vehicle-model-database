import paramiko
import os
import time

SERVER_IP = "112.124.71.198"
USERNAME = "root"
PASSWORD = "caili811229CAILI$" 
REMOTE_PROJECT_PATH = "/root/car_price_predictor"
LOCAL_COMPOSE_FILE = "docker-compose.aliyun.yml"

def deploy_offline():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"Connecting to {SERVER_IP}...")
        client.connect(SERVER_IP, username=USERNAME, password=PASSWORD)
        print("Connected.")
        
        sftp = client.open_sftp()

        # 1. Upload modified docker-compose.aliyun.yml
        print(f"\n[Step 1] Uploading modified {LOCAL_COMPOSE_FILE}...")
        local_path = os.path.join(os.getcwd(), LOCAL_COMPOSE_FILE)
        remote_path = f"{REMOTE_PROJECT_PATH}/{LOCAL_COMPOSE_FILE}"
        sftp.put(local_path, remote_path)
        print("Upload complete.")
        sftp.close()

        # 2. Clean old container
        print("\n[Step 2] Cleaning old container (if exists)...")
        stdin, stdout, stderr = client.exec_command("docker rm -f car_predictor_service car_price_predictor_web car_price_predictor_nginx")
        print(stdout.read().decode())

        # 3. Load Image
        print("\n[Step 3] Loading Docker image (this may take a minute)...")
        stdin, stdout, stderr = client.exec_command(f"docker load -i /root/image.tar.gz")
        # Stream output to avoid timeout perception
        while not stdout.channel.exit_status_ready():
            if stdout.channel.recv_ready():
                print(stdout.channel.recv(1024).decode(), end='')
        print(stdout.read().decode())
        print("Image load complete.")

        # 4. Start Services
        print("\n[Step 4] Starting services with Docker Compose...")
        cmd_up = f"cd {REMOTE_PROJECT_PATH} && docker compose -f {LOCAL_COMPOSE_FILE} up -d"
        stdin, stdout, stderr = client.exec_command(cmd_up)
        print(stdout.read().decode())
        print(stderr.read().decode())

        # 5. Verify
        print("\n[Step 5] Verifying deployment...")
        time.sleep(5) # Wait for containers to initialize
        stdin, stdout, stderr = client.exec_command("docker ps")
        print(stdout.read().decode())
        
        print("\nChecking local access (curl)...")
        stdin, stdout, stderr = client.exec_command("curl -v http://localhost:8096")
        print(stdout.read().decode()[:500] + "...") # Print first 500 chars

    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    deploy_offline()

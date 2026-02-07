import paramiko
import os

SERVER_IP = "112.124.71.198"
USERNAME = "root"
PASSWORD = "caili811229CAILI$" 
REMOTE_PROJECT_PATH = "/root/car_price_predictor"

def check_docker_status():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"Connecting to {SERVER_IP}...")
        client.connect(SERVER_IP, username=USERNAME, password=PASSWORD)
        print("Connected.")
        
        # 1. Check Docker Images
        print("\nChecking Docker Images:")
        stdin, stdout, stderr = client.exec_command("docker images")
        images_output = stdout.read().decode().strip()
        print(images_output)
        
        # 2. Check Docker Containers
        print("\nChecking Docker Containers:")
        stdin, stdout, stderr = client.exec_command("docker ps -a")
        containers_output = stdout.read().decode().strip()
        print(containers_output)

        # 3. Check for image.tar.gz specifically
        print("\nChecking for image.tar.gz:")
        stdin, stdout, stderr = client.exec_command(f"ls -lh {REMOTE_PROJECT_PATH}/image.tar.gz")
        tar_output = stdout.read().decode().strip()
        tar_error = stderr.read().decode().strip()
        if tar_output:
            print(f"Found: {tar_output}")
        else:
            print(f"Not found. Error: {tar_error}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    check_docker_status()

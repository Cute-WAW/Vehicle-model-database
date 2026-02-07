import paramiko
import os
import sys
import tarfile
from io import BytesIO

# Configuration
SERVER_IP = "154.8.205.35"
USERNAME = "root"
PASSWORD = "caili811229CAILI$"
REMOTE_PROJECT_PATH = "/root/car_price_predictor"  # Based on our previous exploration or a sensible default
CONTAINER_NAME = "car-price-predictor-v2"

# Local directories/files to sync
# We sync the 'src' folder (code) and 'nginx' (config) and docker-compose files
# NOTE: Paths must be relative to where the script is run, or absolute. 
# Since we run from project root usually, we should check paths.
BASE_DIR = r"d:\BaiduNetdiskDownload\车型库映射\车型库映射"
PATHS_TO_SYNC = [
    os.path.join(BASE_DIR, "src"),
    os.path.join(BASE_DIR, "nginx"),
    os.path.join(BASE_DIR, "docker-compose.yml"),
    os.path.join(BASE_DIR, "docker-compose.prod.yml"),
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
                # Add file to tar, but strip the absolute base path so it's relative in the tar
                arcname = os.path.relpath(path, BASE_DIR)
                tar.add(path, arcname=arcname)
            else:
                print(f"  Warning: {path} not found, skipping.")
    tar_stream.seek(0)
    return tar_stream

def deploy_update():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"Connecting to {SERVER_IP}...")
        client.connect(SERVER_IP, username=USERNAME, password=PASSWORD)
        print("Connected.")

        # 1. Locate remote project directory explicitly if not sure
        # We try to find where docker-compose.yml is, as we did before
        stdin, stdout, stderr = client.exec_command("find / -name docker-compose.yml 2>/dev/null | head -n 1")
        remote_compose_path = stdout.read().decode().strip()
        
        if not remote_compose_path:
            print("Could not find project on server. Is it deployed?")
            # Optional: Ask to create it? For now, we abort or assume /root/project
            remote_dir = REMOTE_PROJECT_PATH
            print(f"Defaulting to {remote_dir}...")
            client.exec_command(f"mkdir -p {remote_dir}")
        else:
            remote_dir = os.path.dirname(remote_compose_path)
            print(f"Found project at: {remote_dir}")

        # 2. Upload files
        sftp = client.open_sftp()
        tar_data = create_tar_from_paths(PATHS_TO_SYNC)
        
        remote_tar_path = f"{remote_dir}/update_package.tar.gz"
        print(f"Uploading update package to {remote_tar_path}...")
        sftp.putfo(tar_data, remote_tar_path)
        sftp.close()

        # 3. Extract and Apply
        print("Extracting files on server...")
        cmd = f"cd {remote_dir} && tar -xzf update_package.tar.gz && rm update_package.tar.gz"
        stdin, stdout, stderr = client.exec_command(cmd)
        if stdout.channel.recv_exit_status() != 0:
            print(f"Error extracting: {stderr.read().decode()}")
            return

        # 4. Rebuild and Restart
        print("Rebuilding and restarting container...")
        
        # Check if prod file exists
        stdin, stdout, stderr = client.exec_command(f"ls {remote_dir}/docker-compose.prod.yml")
        is_prod = stdout.channel.recv_exit_status() == 0
        compose_file = "docker-compose.prod.yml" if is_prod else "docker-compose.yml"
        print(f"Using {compose_file}...")

        # Define docker compose command (try v2 first, then v1 if needed, but let's default to 'docker compose')
        # We can test which one is available
        dc_cmd = None
        
        # Check for docker compose plugin
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
            # Last resort: assume it's in PATH but maybe PATH is restricted
            # dc_cmd = "docker-compose"
            print("Warning: Could not find docker-compose explicitly. Switching to raw 'docker' commands.")
            dc_cmd = None

        if dc_cmd:
            # Force stop and remove the old container to ensure recreation
            print("Stopping old container...")
            stop_cmd = f"cd {remote_dir} && {dc_cmd} -f {compose_file} down"
            # Also try to remove by name just in case it was started differently
            stop_cmd_2 = f"docker rm -f {CONTAINER_NAME} || true"
            
            client.exec_command(stop_cmd)
            client.exec_command(stop_cmd_2)

            # Build and Up
            restart_cmd = f"cd {remote_dir} && {dc_cmd} -f {compose_file} up --build -d web"
            print(f"Executing: {restart_cmd}")
            
            stdin, stdout, stderr = client.exec_command(restart_cmd)
            
            # Stream output
            exit_status = stdout.channel.recv_exit_status() # Wait for command to finish
            
            out_str = stdout.read().decode()
            err_str = stderr.read().decode()
            
            if out_str: print(f"STDOUT: {out_str}")
            if err_str: print(f"STDERR: {err_str}")
            
            if exit_status != 0:
                print(f"Error executing docker-compose (Exit code {exit_status})")
                # Fallback to raw docker if compose failed
                dc_cmd = None 

        if not dc_cmd:
            print("Using raw docker build/run as fallback...")
            
            # 1. Build
            print("Building image...")
            build_cmd = f"cd {remote_dir} && docker build -t car-price-predictor-img ."
            stdin, stdout, stderr = client.exec_command(build_cmd)
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                print(f"Build failed: {stderr.read().decode()}")
                return

            # 2. Stop/Remove
            print("Removing old container...")
            client.exec_command(f"docker rm -f {CONTAINER_NAME}")

            # 3. Run
            print("Starting new container...")
            # Replicate docker-compose.prod.yml config
            # ports: 8087:8087
            # volumes: ./output:/app/output, ./users.db:/app/users.db
            run_cmd = (
                f"docker run -d --name {CONTAINER_NAME} "
                f"-p 8087:8087 "
                f"-v {remote_dir}/output:/app/output "
                f"-v {remote_dir}/users.db:/app/users.db "
                f"--restart always "
                f"car-price-predictor-img"
            )
            print(f"Executing: {run_cmd}")
            stdin, stdout, stderr = client.exec_command(run_cmd)
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                print(f"Run failed: {stderr.read().decode()}")
            else:
                print("Container started successfully.")
            
        # Verify status
        print("Verifying container status...")
        stdin, stdout, stderr = client.exec_command(f"docker ps | grep {CONTAINER_NAME}")
        print(stdout.read().decode())

        print("\nUpdate completed successfully!")

    except Exception as e:
        print(f"Deployment failed: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    deploy_update()

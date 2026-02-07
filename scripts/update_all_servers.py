import paramiko
import os
import sys
import tarfile
from io import BytesIO
import time

# Configuration
SERVERS = [
    {
        "name": "Tencent Cloud",
        "ip": "154.8.205.35",
        "user": "root",
        "pass": "caili811229CAILI$",
        "compose_file": "docker-compose.prod.yml"
    },
    {
        "name": "Aliyun",
        "ip": "112.124.71.198",
        "user": "root",
        "pass": "caili811229CAILI$",
        "compose_file": "docker-compose.aliyun.yml"
    }
]

BASE_DIR = r"d:\BaiduNetdiskDownload\车型库映射\车型库映射"
PATHS_TO_SYNC = [
    os.path.join(BASE_DIR, "src"),
    os.path.join(BASE_DIR, "nginx"),
    os.path.join(BASE_DIR, "docker-compose.yml"),
    os.path.join(BASE_DIR, "docker-compose.prod.yml"),
    os.path.join(BASE_DIR, "docker-compose.aliyun.yml"),
    os.path.join(BASE_DIR, "requirements.txt"),
    os.path.join(BASE_DIR, "Dockerfile"),
    os.path.join(BASE_DIR, "users.sqlite"),
    os.path.join(BASE_DIR, "output", "merged_residual_value_data.csv"),
    os.path.join(BASE_DIR, "output", "merged_residual_value_data_with_dates.csv"),
    os.path.join(BASE_DIR, "output", "cheyipai_more_residual_value.csv"),
    os.path.join(BASE_DIR, "output", "brand_series_models"),
    os.path.join(BASE_DIR, "output", "car_types_models"),
    os.path.join(BASE_DIR, "price_model")
]

def create_tar_from_paths(paths):
    """Creates a tarball in memory of the specified paths."""
    print("Packing files...")
    tar_stream = BytesIO()
    with tarfile.open(fileobj=tar_stream, mode='w:gz') as tar:
        for path in paths:
            if os.path.exists(path):
                # Add file to tar, but strip the absolute base path so it's relative in the tar
                arcname = os.path.relpath(path, BASE_DIR)
                tar.add(path, arcname=arcname)
            else:
                print(f"  Warning: {path} not found, skipping.")
    tar_stream.seek(0)
    return tar_stream

def update_server(server_config, tar_data):
    print(f"\n=== Updating {server_config['name']} ({server_config['ip']}) ===")
    
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"Connecting...")
        client.connect(server_config['ip'], username=server_config['user'], password=server_config['pass'])
        print("Connected.")

        # 1. Locate remote project directory
        # Try to find where docker-compose file is
        target_file = server_config['compose_file']
        cmd = f"find / -name {target_file} 2>/dev/null | head -n 1"
        stdin, stdout, stderr = client.exec_command(cmd)
        remote_compose_path = stdout.read().decode().strip()
        
        remote_dir = ""
        if not remote_compose_path:
            print(f"Could not find {target_file} on server.")
            # Fallback to common paths or ask to create
            remote_dir = "/root/car_price_predictor"
            print(f"Defaulting to {remote_dir}...")
            client.exec_command(f"mkdir -p {remote_dir}")
        else:
            remote_dir = os.path.dirname(remote_compose_path)
            print(f"Found project at: {remote_dir}")

        # 2. Upload files
        sftp = client.open_sftp()
        # We need to reset the stream position for each server upload
        tar_data.seek(0)
        
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

        # 3.1 Fix users.sqlite (ensure it is a file, not a dir)
        print("Ensuring users.sqlite is a file...")
        # Since we are now uploading users.sqlite in the tarball, we just need to make sure 
        # it wasn't pre-existing as a directory.
        check_cmd = (
            f"cd {remote_dir} && "
            "if [ -d users.sqlite ]; then echo 'Removing directory users.sqlite'; rm -rf users.sqlite; fi && "
            "ls -ld users.sqlite"
        )
        stdin, stdout, stderr = client.exec_command(check_cmd)
        print(f"Fix users.sqlite output:\n{stdout.read().decode()}")

        # 3.2 Clean up potential conflicting containers
        print("Cleaning up potential conflicting containers...")
        # Add nginx containers to cleanup list
        containers = [
            "car_price_predictor", 
            "car_price_predictor_web",
            "car_price_predictor_nginx",
            "nginx_proxy",
            "car-price-predictor-v2"  # Found this old container occupying port 8087 on Tencent Cloud
        ]
        for container in containers:
            # We use || true to ignore error if container doesn't exist
            client.exec_command(f"docker rm -f {container} || true")

        # 3.3 Clean up stale index file on host
        print("Cleaning up stale index file...")
        client.exec_command(f"rm -f {remote_dir}/index/residual_data_index.pkl")
        
        # 4. Restart services
        print(f"Restarting services using {server_config['compose_file']}...")
        
        # Use 'docker-compose' or 'docker compose' depending on availability/version
        # But here we hardcode based on known server env or try both? 
        # The original script used 'docker-compose' for Tencent and 'docker compose' for Aliyun.
        # We will keep that distinction if it was intentional, or standardize.
        # Tencent (154...) usually has docker-compose. Aliyun (112...) has docker compose plugin.
        
        compose_cmd = "docker-compose" if "prod" in server_config['compose_file'] else "docker compose"
        
        # Try down first to clear state, then up
        # Add --build to ensure image is rebuilt with new code/dependencies (especially for Tencent Cloud which uses build: .)
        restart_cmd = (
            f"cd {remote_dir} && "
            f"{compose_cmd} -f {server_config['compose_file']} down --remove-orphans || true && "
            f"{compose_cmd} -f {server_config['compose_file']} up -d --build --force-recreate"
        )
        
        print(f"Executing: {restart_cmd}")
        stdin, stdout, stderr = client.exec_command(restart_cmd)
        
        exit_status = stdout.channel.recv_exit_status()
        if exit_status == 0:
            print(f"Success! Output:\n{stdout.read().decode()}")
        else:
            print(f"Error restarting: {stderr.read().decode()}")

    except Exception as e:
        print(f"Failed to update {server_config['name']}: {e}")
    finally:
        client.close()

def main():
    # Prepare the tarball once
    tar_data = create_tar_from_paths(PATHS_TO_SYNC)
    
    for server in SERVERS:
        update_server(server, tar_data)

if __name__ == "__main__":
    main()

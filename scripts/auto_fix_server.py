import paramiko
import sys
import time

def auto_fix(hostname, username, password):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"Connecting to {hostname}...")
        client.connect(hostname, username=username, password=password)
        print("Connected successfully.")

        # 1. Check if port 80 is in use
        print("\nChecking port 80 usage...")
        # Use a stricter grep to avoid matching 8080, 8087, etc.
        # We look for ":80 " (with space) or ":80$" (end of line)
        stdin, stdout, stderr = client.exec_command("netstat -tulpn | grep -E ':80\\s|:80$'")
        out = stdout.read().decode().strip()
        
        # Double check if any line actually contains ":80" specifically
        is_port_80_used = False
        if out:
            for line in out.split('\n'):
                parts = line.split()
                if len(parts) >= 4:
                    local_address = parts[3]
                    if local_address.endswith(':80'):
                        is_port_80_used = True
                        break
        
        if is_port_80_used:
            print(f"Port 80 is in use:\n{out}")
            # Check if it's nginx
            if "nginx" in out:
                print("Nginx is running on port 80. We might need to configure it.")
            else:
                print("Port 80 is occupied by another process. Cannot automatically switch.")
                return
        else:
            print("Port 80 is free.")
            
            # 2. Find the project directory via running container
            print("\nLocating project directory via docker inspect...")
            stdin, stdout, stderr = client.exec_command("docker ps -q --filter name=car_price_predictor")
            container_id = stdout.read().decode().strip()
            
            project_dir = ""
            if container_id:
                # Inspect mounts to find where the code is
                cmd = f"docker inspect -f '{{{{range .Mounts}}}}{{{{if eq .Type \"bind\"}}}}{{{{.Source}}}}{{{{end}}}}{{{{end}}}}' {container_id}"
                stdin, stdout, stderr = client.exec_command(cmd)
                mount_source = stdout.read().decode().strip()
                if mount_source:
                    # Usually mounts are like /path/to/project/output -> /app/output
                    # So we take the parent of the mount source
                    import os
                    # If mount is /root/project/output, project dir is /root/project
                    # Let's try to guess based on common mounts
                    # We know we mount ./output and ./users.db
                    if "output" in mount_source:
                         project_dir = mount_source.split("/output")[0]
                    elif "users.db" in mount_source:
                         project_dir = mount_source.split("/users.db")[0]
                    else:
                         # Fallback: just list root
                         project_dir = "/root" # Assumption
                else:
                    print("No bind mounts found. Searching /root...")
                    project_dir = "/root"
            else:
                print("Container not running. Searching common paths...")
                # Try to find folder with docker-compose.yml in /root
                stdin, stdout, stderr = client.exec_command("find /root -name docker-compose.yml -maxdepth 3")
                paths = stdout.read().decode().strip().split('\n')
                if paths and paths[0]:
                    project_dir = paths[0].replace("/docker-compose.yml", "")
                else:
                    print("Could not find docker-compose.yml")
                    return

            print(f"Project directory appears to be: {project_dir}")
            compose_path = f"{project_dir}/docker-compose.yml"
            
            # Check if file exists
            stdin, stdout, stderr = client.exec_command(f"ls {compose_path}")
            if stdout.channel.recv_exit_status() != 0:
                print(f"docker-compose.yml not found at {compose_path}")
                # Try finding again if my deduction failed
                stdin, stdout, stderr = client.exec_command("find / -name docker-compose.yml 2>/dev/null | head -n 1")
                compose_path = stdout.read().decode().strip()
                if not compose_path:
                    print("Really could not find docker-compose.yml.")
                    return
                project_dir = compose_path.replace("/docker-compose.yml", "")
            
            # 3. Modify docker-compose.yml to use port 80
            print("\nModifying docker-compose.yml to use port 80...")
            # Backup first
            client.exec_command(f"cp {compose_path} {compose_path}.bak")
            
            # Use sed to replace port mapping. 
            # Assuming the line is like '- "8087:8087"' or similar. 
            # We want to change the host port (left side) to 80.
            # Pattern: replace "8087:8087" with "80:8087"
            cmd = f"sed -i 's/8087:8087/80:8087/g' {compose_path}"
            stdin, stdout, stderr = client.exec_command(cmd)
            error = stderr.read().decode().strip()
            if error:
                print(f"Error modifying file: {error}")
                return
            
            print("Successfully updated docker-compose.yml.")
            
            # 4. Restart containers
            print("\nRestarting containers...")
            stdin, stdout, stderr = client.exec_command(f"cd {project_dir} && docker-compose down && docker-compose up -d")
            
            # Wait for output
            while not stdout.channel.exit_status_ready():
                time.sleep(1)
            
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            print(out)
            if err:
                print(f"Docker output/error: {err}")
                
            print("\nContainer restarted. Please try accessing http://154.8.205.35/ (Port 80)")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python auto_fix_server.py <host> <user> <password>")
        sys.exit(1)
        
    host = sys.argv[1]
    user = sys.argv[2]
    pwd = sys.argv[3]
    
    auto_fix(host, user, pwd)

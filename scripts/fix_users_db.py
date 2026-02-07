
import paramiko
import os

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

def fix_users_db(server):
    print(f"\n=== Fixing users.db on {server['name']} ===")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(server['ip'], username=server['user'], password=server['pass'])
        
        # 1. Stop containers
        print("Stopping containers...")
        client.exec_command(f"cd /root/car_price_predictor && docker-compose -f {server['compose_file']} down")
        
        # 2. Check if users.db is a directory and remove it
        print("Checking users.db...")
        stdin, stdout, stderr = client.exec_command("ls -ld /root/car_price_predictor/users.db")
        output = stdout.read().decode()
        if "drwx" in output:
            print("Found directory users.db. Removing...")
            client.exec_command("rm -rf /root/car_price_predictor/users.db")
        
        # 3. Create empty users.db file
        print("Creating empty users.db file...")
        client.exec_command("touch /root/car_price_predictor/users.db")
        
        # 4. Restart containers
        print("Restarting containers...")
        # Use force-recreate to be sure
        cmd = f"cd /root/car_price_predictor && docker-compose -f {server['compose_file']} up -d"
        client.exec_command(cmd)
        
        print("Done.")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    for server in SERVERS:
        fix_users_db(server)

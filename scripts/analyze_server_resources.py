import paramiko
import time

SERVER_IP = "112.124.71.198"
USERNAME = "root"
PASSWORD = "caili811229CAILI$"

def analyze_server():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"Connecting to {SERVER_IP}...")
        client.connect(SERVER_IP, username=USERNAME, password=PASSWORD, timeout=10)
        print("Connected.\n")
        
        commands = [
            ("System Load & Uptime", "uptime"),
            ("Memory Usage", "free -h"),
            ("Disk Usage", "df -h"),
            ("Docker Service Status", "systemctl status docker --no-pager -n 10"),
            ("Docker Daemon Config", "cat /etc/docker/daemon.json"),
            ("Running Containers", "docker ps -a --format 'table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}'"),
            ("Docker Stats (Resource Usage)", "docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}'")
        ]

        for title, cmd in commands:
            print(f"=== {title} ===")
            try:
                stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
                out = stdout.read().decode().strip()
                err = stderr.read().decode().strip()
                
                if out:
                    print(out)
                if err:
                    print(f"[STDERR] {err}")
            except Exception as e:
                print(f"Error executing command: {e}")
            print("\n")

    except Exception as e:
        print(f"Connection failed: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    analyze_server()

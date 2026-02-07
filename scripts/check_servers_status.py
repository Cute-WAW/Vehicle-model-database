import paramiko
import os

SERVERS = [
    {
        "name": "Tencent Cloud",
        "ip": "154.8.205.35",
        "user": "root",
        "pass": "caili811229CAILI$"
    },
    {
        "name": "Aliyun",
        "ip": "112.124.71.198",
        "user": "root",
        "pass": "caili811229CAILI$"
    }
]

def check_server(server):
    print(f"\n=== Checking {server['name']} ({server['ip']}) ===")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(server['ip'], username=server['user'], password=server['pass'])
        stdin, stdout, stderr = client.exec_command("docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")
        print(stdout.read().decode())
        client.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    for server in SERVERS:
        check_server(server)

import paramiko
import os

SERVERS = [
    {
        "name": "Tencent Cloud",
        "ip": "154.8.205.35",
        "user": "root",
        "pass": "caili811229CAILI$",
        "container": "car_price_predictor"
    },
    {
        "name": "Aliyun",
        "ip": "112.124.71.198",
        "user": "root",
        "pass": "caili811229CAILI$",
        "container": "car_price_predictor_web"
    }
]

def check_server(server):
    print(f"\n=== Diagnosing {server['name']} ({server['ip']}) ===")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(server['ip'], username=server['user'], password=server['pass'])
        
        # 1. Check if home.html contains "month" (the new change)
        print("Checking home.html content...")
        cmd = "grep 'type=\"month\"' /root/car_price_predictor/src/web/templates/home.html"
        stdin, stdout, stderr = client.exec_command(cmd)
        exit_code = stdout.channel.recv_exit_status()
        if exit_code == 0:
            print("  [OK] home.html contains 'type=\"month\"'")
        else:
            print("  [FAIL] home.html DOES NOT contain 'type=\"month\"'. Old version?")
            
        # 2. Check container logs (last 20 lines)
        print("Checking container logs...")
        stdin, stdout, stderr = client.exec_command(f"docker logs --tail 20 {server['container']}")
        print(stdout.read().decode())
        print(stderr.read().decode())
        
        # 3. Check if captcha is installed
        print("Checking pip list in container...")
        stdin, stdout, stderr = client.exec_command(f"docker exec {server['container']} pip list | grep captcha")
        print(stdout.read().decode())
        
        # 4. Check users.sqlite status
        print("Checking users.sqlite status...")
        cmd = "ls -ld /root/car_price_predictor/users.sqlite"
        stdin, stdout, stderr = client.exec_command(cmd)
        output = stdout.read().decode().strip()
        print(f"  {output}")
        
        # 5. Check login.html content
        print("Checking login.html content for captcha...")
        cmd = "grep 'captcha' /root/car_price_predictor/src/web/templates/login.html"
        stdin, stdout, stderr = client.exec_command(cmd)
        if stdout.channel.recv_exit_status() == 0:
            print("  [OK] login.html contains 'captcha'")
        else:
            print("  [FAIL] login.html DOES NOT contain 'captcha'. Old version?")
            
        client.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    for server in SERVERS:
        check_server(server)

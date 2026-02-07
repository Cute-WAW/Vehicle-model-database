import paramiko
import os

SERVER = {
    "name": "Aliyun",
    "ip": "112.124.71.198",
    "user": "root",
    "pass": "caili811229CAILI$",
    "container": "car_price_predictor_web"
}

def check_aliyun_logs():
    print(f"\n=== Checking logs for {SERVER['name']} ({SERVER['ip']}) ===")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(SERVER['ip'], username=SERVER['user'], password=SERVER['pass'])
        
        print("Fetching container logs...")
        stdin, stdout, stderr = client.exec_command(f"docker logs --tail 50 {SERVER['container']}")
        print(stdout.read().decode())
        print(stderr.read().decode())
        
        client.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_aliyun_logs()

import paramiko
import time

SERVERS = [
    {
        "name": "Tencent Cloud",
        "ip": "154.8.205.35",
        "user": "root",
        "pass": "caili811229CAILI$",
        "web_container": "car_price_predictor", # from docker-compose.prod.yml
        "nginx_container": "nginx_proxy"
    },
    {
        "name": "Aliyun",
        "ip": "112.124.71.198",
        "user": "root",
        "pass": "caili811229CAILI$",
        "web_container": "car_price_predictor_web", # from docker-compose.aliyun.yml
        "nginx_container": "car_price_predictor_nginx"
    }
]

def diagnose(server):
    print(f"\n=== Diagnosing {server['name']} ({server['ip']}) ===")
    
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(server['ip'], username=server['user'], password=server['pass'])
        
        # 1. Check container status
        print("\n[1] Container Status:")
        stdin, stdout, stderr = client.exec_command("docker ps -a")
        print(stdout.read().decode())
        
        # 2. Check Web Container Logs
        web_c = server['web_container']
        print(f"\n[2] Logs for {web_c}:")
        stdin, stdout, stderr = client.exec_command(f"docker logs --tail 20 {web_c}")
        logs = stdout.read().decode() + stderr.read().decode()
        print(logs)
        
        # 3. Check Nginx Container Logs
        nginx_c = server['nginx_container']
        print(f"\n[3] Logs for {nginx_c}:")
        stdin, stdout, stderr = client.exec_command(f"docker logs --tail 20 {nginx_c}")
        logs = stdout.read().decode() + stderr.read().decode()
        print(logs)
        
        # 4. Check File Structure
        print("\n[4] File Structure Check:")
        stdin, stdout, stderr = client.exec_command("ls -R /root/car_price_predictor/src | head -n 10")
        print(stdout.read().decode())
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    for server in SERVERS:
        diagnose(server)

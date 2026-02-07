import paramiko
import sys

def check_aliyun():
    host = "112.124.71.198"
    user = "root"
    password = "caili811229CAILI$"
    
    print(f"Connecting to {host}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(host, username=user, password=password)
        print("Connected.")
        
        commands = [
            "docker ps -a | grep car_price",
            "docker logs --tail 20 car_price_predictor_web"
        ]
        
        for cmd in commands:
            print(f"\nRunning: {cmd}")
            stdin, stdout, stderr = client.exec_command(cmd)
            out = stdout.read().decode()
            err = stderr.read().decode()
            if out: print(f"Output:\n{out}")
            if err: print(f"Error:\n{err}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    check_aliyun()

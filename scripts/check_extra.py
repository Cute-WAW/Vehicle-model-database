import paramiko
import os

SERVER_IP = "112.124.71.198"
USERNAME = "root"
PASSWORD = "caili811229CAILI$" 

def check_extra():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"Connecting to {SERVER_IP}...")
        client.connect(SERVER_IP, username=USERNAME, password=PASSWORD)
        print("Connected.")
        
        # 1. Check image.tar.gz in root
        print("\nChecking /root/image.tar.gz:")
        stdin, stdout, stderr = client.exec_command("ls -lh /root/image.tar.gz")
        print(stdout.read().decode().strip() or stderr.read().decode().strip())

        # 2. Check curl localhost:8096
        print("\nChecking curl localhost:8096:")
        stdin, stdout, stderr = client.exec_command("curl -v http://localhost:8096")
        print(stdout.read().decode().strip() or stderr.read().decode().strip())
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    check_extra()

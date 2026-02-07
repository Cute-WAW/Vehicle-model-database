import paramiko
import os
import time

SERVER_IP = "112.124.71.198"
USERNAME = "root"
PASSWORD = "caili811229CAILI$" 
REMOTE_PROJECT_PATH = "/root/car_price_predictor"
LOCAL_DATA_FILE = "output/merged_residual_value_data.csv"

def fix_data():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"Connecting to {SERVER_IP}...")
        client.connect(SERVER_IP, username=USERNAME, password=PASSWORD)
        print("Connected.")
        
        sftp = client.open_sftp()

        # 1. Upload Data File
        print(f"\n[Step 1] Uploading {LOCAL_DATA_FILE}...")
        local_path = os.path.join(os.getcwd(), LOCAL_DATA_FILE)
        remote_path = f"{REMOTE_PROJECT_PATH}/{LOCAL_DATA_FILE}"
        
        if not os.path.exists(local_path):
             print(f"Error: Local file {local_path} not found!")
             return

        file_size = os.path.getsize(local_path)
        print(f"File size: {file_size / (1024*1024):.2f} MB")
        
        def progress(transferred, total):
            percent = (transferred / total) * 100
            print(f"\rTransferred: {transferred / (1024*1024):.2f} MB ({percent:.1f}%)", end='')
            
        sftp.put(local_path, remote_path, callback=progress)
        print("\nUpload complete.")
        sftp.close()

        # 2. Restart Web Container
        print("\n[Step 2] Restarting web container to load data...")
        stdin, stdout, stderr = client.exec_command("docker restart car_price_predictor_web")
        print(stdout.read().decode())
        
        # 3. Verify Logs
        print("\n[Step 3] Checking logs for data loading...")
        time.sleep(10) # Wait for startup
        stdin, stdout, stderr = client.exec_command("docker logs car_price_predictor_web --tail 50")
        logs = stdout.read().decode()
        print(logs)
        
        if "merged_residual_value_data.csv" in logs:
            print("\n[SUCCESS] Data loaded successfully!")
        else:
            print("\n[WARNING] Could not confirm data loading from logs. Please check manually.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    fix_data()

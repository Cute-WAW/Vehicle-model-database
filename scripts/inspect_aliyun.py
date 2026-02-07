import paramiko
import os

SERVERS = [
    {
        "name": "Aliyun",
        "ip": "112.124.71.198",
        "user": "root",
        "pass": "caili811229CAILI$",
        "compose_file": "docker-compose.aliyun.yml"
    }
]

def run_cmd(client, cmd):
    stdin, stdout, stderr = client.exec_command(cmd)
    code = stdout.channel.recv_exit_status()
    out = stdout.read().decode(errors="ignore")
    err = stderr.read().decode(errors="ignore")
    return code, out, err

def main():
    s = SERVERS[0]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(s["ip"], username=s["user"], password=s["pass"])
    code, out, err = run_cmd(client, f"find / -name {s['compose_file']} 2>/dev/null | head -n 1")
    remote_compose_path = out.strip()
    if not remote_compose_path:
        print("compose file not found")
        client.close()
        return
    remote_dir = os.path.dirname(remote_compose_path)
    print(f"remote_dir={remote_dir}")
    cmds = [
        f"cd {remote_dir} && ls -l output | head -n 50",
        f"cd {remote_dir} && ls -l price_model/brand_series_model | head -n 50",
        f"cd {remote_dir} && ls -l price_model/brand_series_model | grep -n \"大众-朗逸.pkl\" || true",
        f"cd {remote_dir} && grep -n \"merged_residual_value_data_with_dates.csv\" src/web_predictor_debug_step5.py || true",
        f"cd {remote_dir} && grep -n \"merged_residual_value_data_with_dates.csv\" src/residual_predictor_step5.py || true",
        f"cd {remote_dir} && ls -l index | head -n 50",
        f"cd {remote_dir} && docker compose -f {s['compose_file']} ps",
        f"cd {remote_dir} && docker compose -f {s['compose_file']} logs -n 200 --tail 200",
        "curl -s -i -X POST http://127.0.0.1:8087/predict -H 'Content-Type: application/json' -d '{\"vehicle_full_name\":\"大众 朗逸三厢 2023款 1.5L 自动 五百万版\",\"brand_series\":\"大众-朗逸\",\"years\":1.0,\"grade\":\"中\",\"city\":\"郑州\",\"mileage\":1.0,\"new_price\":null}'",
        f"cd {remote_dir} && docker compose -f {s['compose_file']} logs --tail 50 web"
    ]
    for cmd in cmds:
        print(f"$ {cmd}")
        code, out, err = run_cmd(client, cmd)
        print(out)
        if err:
            print(err)
    client.close()

if __name__ == "__main__":
    main()

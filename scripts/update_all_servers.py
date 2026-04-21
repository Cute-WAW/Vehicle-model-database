import json
import os
import tarfile
from io import BytesIO

import paramiko


SERVERS = [
    {
        "name": "Tencent Cloud",
        "ip": "154.8.205.35",
        "user": "root",
        "pass": "caili811229CAILI$",
        "compose_file": "docker-compose.prod.yml",
        "compose_cmd": "docker-compose",
        "health_url": "http://127.0.0.1:8087/health",
        "web_container": "car_price_predictor",
        "sidecar_containers": ["nginx_proxy"],
    },
    {
        "name": "Aliyun",
        "ip": "112.124.71.198",
        "user": "root",
        "pass": "caili811229CAILI$",
        "compose_file": "docker-compose.aliyun.yml",
        "compose_cmd": "docker compose",
        "health_url": "http://127.0.0.1:8096/health",
        "web_container": "car_price_predictor_web",
        "sidecar_containers": ["car_price_predictor_nginx"],
    },
]

BASE_DIR = r"d:\BaiduNetdiskDownload\车型库映射\车型库映射"
PATHS_TO_SYNC = [
    os.path.join(BASE_DIR, "src"),
    os.path.join(BASE_DIR, "config"),
    os.path.join(BASE_DIR, "nginx"),
    os.path.join(BASE_DIR, "wechat"),
    os.path.join(BASE_DIR, "doc"),
    os.path.join(BASE_DIR, "experiment"),
    os.path.join(BASE_DIR, "tests"),
    os.path.join(BASE_DIR, "docker-compose.yml"),
    os.path.join(BASE_DIR, "docker-compose.prod.yml"),
    os.path.join(BASE_DIR, "docker-compose.aliyun.yml"),
    os.path.join(BASE_DIR, "requirements.txt"),
    os.path.join(BASE_DIR, "Dockerfile"),
    os.path.join(BASE_DIR, "users.sqlite"),
    os.path.join(BASE_DIR, "output", "merged_residual_value_data.csv"),
    os.path.join(BASE_DIR, "output", "merged_residual_value_data_with_dates.csv"),
    os.path.join(BASE_DIR, "output", "cheyipai_more_residual_value.csv"),
    os.path.join(BASE_DIR, "output", "brand_series_models"),
    os.path.join(BASE_DIR, "output", "car_types_models"),
    os.path.join(BASE_DIR, "output", "segmented_models"),
    os.path.join(BASE_DIR, "output", "lightgbm"),
    os.path.join(BASE_DIR, "price_model"),
]

CONTAINERS_TO_CLEAN = [
    "car_price_predictor",
    "car_price_predictor_web",
    "car_price_predictor_nginx",
    "nginx_proxy",
    "car-price-predictor-v2",
]


def create_tar_from_paths(paths):
    """Create a tarball in memory for the selected project paths."""
    print("Packing files...")
    tar_stream = BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w:gz") as tar:
        for path in paths:
            if os.path.exists(path):
                arcname = os.path.relpath(path, BASE_DIR)
                tar.add(path, arcname=arcname)
            else:
                print(f"  Warning: {path} not found, skipping.")
    tar_stream.seek(0)
    return tar_stream


def run_cmd(client, cmd, timeout=1800):
    """Execute a remote shell command and return structured output."""
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    return {
        "cmd": cmd,
        "exit_code": exit_code,
        "stdout": stdout.read().decode(errors="ignore"),
        "stderr": stderr.read().decode(errors="ignore"),
    }


def print_result(prefix, result):
    """Pretty-print command execution output."""
    print(f"{prefix} [exit={result['exit_code']}]")
    if result["stdout"].strip():
        print(result["stdout"])
    if result["stderr"].strip():
        print(result["stderr"])


def locate_remote_dir(client, compose_file):
    """Locate remote project directory by compose file."""
    result = run_cmd(client, f"find / -name {compose_file} 2>/dev/null | head -n 1", timeout=60)
    compose_path = result["stdout"].strip()
    if compose_path:
        return os.path.dirname(compose_path)
    return "/root/car_price_predictor"


def upload_package(client, remote_dir, tar_data):
    """Upload the update tarball to the target server."""
    tar_data.seek(0)
    remote_tar_path = f"{remote_dir}/update_package.tar.gz"
    print(f"Uploading update package to {remote_tar_path}...")
    sftp = client.open_sftp()
    try:
        sftp.putfo(tar_data, remote_tar_path)
    finally:
        sftp.close()
    return remote_tar_path


def extract_package(client, remote_dir):
    """Extract the uploaded tarball on the remote server."""
    cmd = f"cd {remote_dir} && tar -xzf update_package.tar.gz && rm update_package.tar.gz"
    return run_cmd(client, cmd)


def fix_sqlite_file(client, remote_dir):
    """Ensure users.sqlite remains a file instead of an accidental directory."""
    cmd = (
        f"cd {remote_dir} && "
        "if [ -d users.sqlite ]; then echo 'Removing directory users.sqlite'; rm -rf users.sqlite; fi && "
        "ls -ld users.sqlite"
    )
    return run_cmd(client, cmd, timeout=60)


def cleanup_containers(client):
    """Remove potentially conflicting containers before restart."""
    for container in CONTAINERS_TO_CLEAN:
        run_cmd(client, f"docker rm -f {container} || true", timeout=120)


def cleanup_index(client, remote_dir):
    """Remove stale residual-data index so runtime rebuilds it from fresh CSV."""
    return run_cmd(client, f"rm -f {remote_dir}/index/residual_data_index.pkl", timeout=60)


def compose_up_build(client, remote_dir, compose_cmd, compose_file):
    """Bring the service up with a full rebuild."""
    cmd = (
        f"cd {remote_dir} && "
        f"{compose_cmd} -f {compose_file} down --remove-orphans || true && "
        f"{compose_cmd} -f {compose_file} up -d --build --force-recreate"
    )
    return run_cmd(client, cmd, timeout=3600)


def compose_up_no_build(client, remote_dir, compose_cmd, compose_file):
    """Fallback path that starts services from the existing image cache."""
    cmd = (
        f"cd {remote_dir} && "
        f"{compose_cmd} -f {compose_file} up -d --force-recreate --no-build"
    )
    return run_cmd(client, cmd, timeout=1800)


def apply_runtime_patch(client, remote_dir, server_config):
    """Patch a running container when image rebuild is blocked by registry issues."""
    web_container = server_config["web_container"]
    sidecars = " ".join(server_config["sidecar_containers"])
    commands = [
        f"docker cp {remote_dir}/config/. {web_container}:/app/config/",
        f"docker exec {web_container} pip install --no-cache-dir -r /app/requirements.txt -i https://mirrors.aliyun.com/pypi/simple/",
        f"docker restart {web_container} {sidecars}",
    ]
    results = []
    for cmd in commands:
        results.append(run_cmd(client, cmd, timeout=3600))
    return results


def health_check(client, health_url):
    """Check the remote health endpoint."""
    cmd = f"bash -lc \"sleep 8; curl -s {health_url} || wget -qO- {health_url} || echo HEALTH_CHECK_FAILED\""
    return run_cmd(client, cmd, timeout=60)


def docker_ps(client):
    """List running containers for visibility after deployment."""
    return run_cmd(client, "docker ps --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}'", timeout=60)


def update_server(server_config, tar_data):
    print(f"\n=== Updating {server_config['name']} ({server_config['ip']}) ===")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    summary = {
        "server": server_config["name"],
        "ip": server_config["ip"],
        "remote_dir": "",
        "mode": "build",
        "status": "unknown",
        "health": "",
        "steps": [],
    }

    try:
        print("Connecting...")
        client.connect(server_config["ip"], username=server_config["user"], password=server_config["pass"], timeout=15)
        print("Connected.")

        remote_dir = locate_remote_dir(client, server_config["compose_file"])
        summary["remote_dir"] = remote_dir
        print(f"Using project directory: {remote_dir}")

        upload_package(client, remote_dir, tar_data)
        extract_result = extract_package(client, remote_dir)
        print_result("Extract package", extract_result)
        summary["steps"].append(extract_result)
        if extract_result["exit_code"] != 0:
            summary["status"] = "extract_failed"
            return summary

        sqlite_result = fix_sqlite_file(client, remote_dir)
        print_result("Fix users.sqlite", sqlite_result)
        summary["steps"].append(sqlite_result)

        cleanup_containers(client)
        cleanup_index_result = cleanup_index(client, remote_dir)
        print_result("Cleanup stale index", cleanup_index_result)
        summary["steps"].append(cleanup_index_result)

        build_result = compose_up_build(
            client,
            remote_dir,
            server_config["compose_cmd"],
            server_config["compose_file"],
        )
        print_result("Compose up --build", build_result)
        summary["steps"].append(build_result)

        if build_result["exit_code"] != 0:
            summary["mode"] = "fallback_no_build"
            print("Build path failed, switching to fallback recovery mode...")
            no_build_result = compose_up_no_build(
                client,
                remote_dir,
                server_config["compose_cmd"],
                server_config["compose_file"],
            )
            print_result("Compose up --no-build", no_build_result)
            summary["steps"].append(no_build_result)

            if no_build_result["exit_code"] == 0:
                patch_results = apply_runtime_patch(client, remote_dir, server_config)
                for idx, result in enumerate(patch_results, start=1):
                    print_result(f"Runtime patch step {idx}", result)
                    summary["steps"].append(result)
            else:
                summary["status"] = "restart_failed"
                return summary

        health_result = health_check(client, server_config["health_url"])
        print_result("Health check", health_result)
        summary["steps"].append(health_result)
        summary["health"] = health_result["stdout"].strip()

        docker_ps_result = docker_ps(client)
        print_result("docker ps", docker_ps_result)
        summary["steps"].append(docker_ps_result)

        if health_result["exit_code"] == 0 and "predictor_ready" in health_result["stdout"]:
            summary["status"] = "ok"
        else:
            summary["status"] = "health_failed"

        return summary
    except Exception as e:
        summary["status"] = "exception"
        summary["error"] = str(e)
        print(f"Failed to update {server_config['name']}: {e}")
        return summary
    finally:
        try:
            client.close()
        except Exception:
            pass


def main():
    tar_data = create_tar_from_paths(PATHS_TO_SYNC)
    summaries = []
    for server in SERVERS:
        summaries.append(update_server(server, tar_data))

    print("\n=== Update Summary ===")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

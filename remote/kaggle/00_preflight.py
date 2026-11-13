# ScriptShield — Kaggle preflight (NO model weights, NO heavy installs)
#
# Purpose: resolve B-003. Record Python/GPU/disk/internet facts and verify that
# the three pinned toolkits can be installed and IMPORTED in this image.
# Cost: $0 (free Kaggle quota). No HF weights are downloaded.
#
# Run as a Kaggle notebook with GPU enabled and Internet on.
# Secrets: add HF_TOKEN via Add-ons > Secrets. Never paste a token into a cell.

import json, os, platform, shutil, subprocess, sys, time

REPORT = {"stage": "preflight", "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        return None

# --- 1. environment facts ---
REPORT["python"] = sys.version
REPORT["python_ok_for_safetune"] = sys.version_info >= (3, 12)
REPORT["platform"] = platform.platform()
try:
    import torch
    REPORT["torch"] = torch.__version__
    REPORT["cuda_available"] = torch.cuda.is_available()
    REPORT["gpu_names"] = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
    REPORT["vram_gb"] = [round(torch.cuda.get_device_properties(i).total_memory/1e9, 2)
                         for i in range(torch.cuda.device_count())]
except Exception as e:
    REPORT["torch"] = f"ABSENT: {type(e).__name__}"
    REPORT["cuda_available"] = False
r = sh("nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader")
REPORT["nvidia_smi"] = r.stdout.strip() if r and r.returncode == 0 else "unavailable"
du = shutil.disk_usage("/kaggle/working")
REPORT["working_disk_free_gb"] = round(du.free/1e9, 2)
REPORT["cpu_count"] = os.cpu_count()

# --- 2. internet + HF gate status (metadata only, no weights) ---
token = None
try:
    from kaggle_secrets import UserSecretsClient
    token = UserSecretsClient().get_secret("HF_TOKEN")
    REPORT["hf_secret_present"] = True
except Exception as e:
    REPORT["hf_secret_present"] = False
    REPORT["hf_secret_error"] = type(e).__name__

import urllib.request
def probe(url, auth=False):
    req = urllib.request.Request(url)
    if auth and token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return f"ERR:{type(e).__name__}"

REPORT["hf_reachable"] = probe("https://huggingface.co/api/models/CohereLabs/tiny-aya-fire", auth=True)
REPORT["fire_config_status"] = probe(
    "https://huggingface.co/CohereLabs/tiny-aya-fire/resolve/main/config.json", auth=True)
REPORT["global_config_status"] = probe(
    "https://huggingface.co/CohereLabs/tiny-aya-global/resolve/main/config.json", auth=True)
REPORT["gate_open"] = REPORT["fire_config_status"] == 200

# --- 3. pinned toolkit installs, then IMPORT verification ---
PINS = {
    "AuditKIT":   ("71316da345784ff220d5ed59337441a59ab31526", "auditkit",   True),
    "CuratorKIT": ("dd9e835301fcddc74a37501d9e207a5a060d209f", "curatorkit", True),
    "SafeTune":   ("26f59e6d1bdcacafe5f2be3b8d982fb214369659", "safetune",   False),
}
REPORT["installs"] = {}
for name, (sha, mod, no_deps) in PINS.items():
    url = f"git+https://github.com/Lexsi-Labs/{name}@{sha}"
    cmd = f"{sys.executable} -m pip install -q " + ("--no-deps " if no_deps else "") + f"'{url}'"
    r = sh(cmd)
    entry = {"pip_returncode": (r.returncode if r else "timeout"), "sha": sha}
    if r and r.returncode != 0:
        entry["pip_stderr_tail"] = r.stderr[-1500:]
    # pip exit 0 is NOT success. Verify the import.
    try:
        m = __import__(mod)
        entry["import_ok"] = True
        entry["version"] = getattr(m, "__version__", "unknown")
    except Exception as e:
        entry["import_ok"] = False
        entry["import_error"] = f"{type(e).__name__}: {e}"[:600]
    REPORT["installs"][name] = entry

# --- 4. required symbols ---
REPORT["symbols"] = {}
for label, stmt in {
    "curatorkit.Curator": "from curatorkit import Curator, CuratorConfig",
    "auditkit.evaluate": "from auditkit import evaluate, generate, Sample",
    "safetune.caa": "from safetune.interventions.steer.caa import CAAModel, extract_caa_vectors",
}.items():
    try:
        exec(stmt, {})
        REPORT["symbols"][label] = "OK"
    except Exception as e:
        REPORT["symbols"][label] = f"{type(e).__name__}: {e}"[:400]

REPORT["verdict"] = {
    "gpu_usable": bool(REPORT.get("cuda_available")),
    "python_ok": REPORT["python_ok_for_safetune"],
    "gate_open": REPORT["gate_open"],
    "all_symbols_ok": all(v == "OK" for v in REPORT["symbols"].values()),
}
print(json.dumps(REPORT, indent=2))
with open("/kaggle/working/preflight_report.json", "w") as f:
    json.dump(REPORT, f, indent=2)
print("\nSaved /kaggle/working/preflight_report.json")
print("NEXT: if gate_open is False, B-001 still blocks the model smoke test.")

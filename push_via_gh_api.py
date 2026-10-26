import base64
import json
import subprocess
from pathlib import Path

REPO = "AIjennings/ariawave-metacognition"
ROOT = Path(r"C:\Users\Aria\Documents\ariawave-metacognition")

FILES = [
    "README.md",
    "LICENSE",
    "SKILL.md",
    "metacognition_auditor.py",
    "skills/metacognition-engine/SKILL.md",
    "skills/metacognition-engine/metacognition_auditor.py",
]

for rel in FILES:
    raw = (ROOT / rel).read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    # check if exists
    chk = subprocess.run(["gh", "api", f"repos/{REPO}/contents/{rel}", "--jq", ".sha"], capture_output=True, text=True)
    body = {
        "message": f"feat: upgrade {rel} to v1.1.0",
        "content": b64,
    }
    if chk.returncode == 0 and chk.stdout.strip():
        body["sha"] = chk.stdout.strip()

    cmd = ["gh", "api", "--method", "PUT", f"repos/{REPO}/contents/{rel}", "--input", "-"]
    r = subprocess.run(cmd, input=json.dumps(body), capture_output=True, text=True)
    if r.returncode != 0:
        print(f"Error publishing {rel}: {r.stderr.strip()}")
    else:
        print(f"Published {rel} -> rc={r.returncode}")

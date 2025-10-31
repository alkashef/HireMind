from pathlib import Path
import json
import sys

# Ensure project root is on sys.path so `import utils` works when running this script
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.hermes_client import HermesClient

# Create client but stub .generate to avoid loading heavy model
h = HermesClient(model_dir="models/hermes-pro", quantize_4bit=False)
h.generate = lambda prompt, **k: prompt

# Load canonical test JSON and extract 'text'
p = Path(__file__).resolve().parents[1] / "tests" / "data" / "Ahmad Alkashef - Resume.json"
if p.exists():
    try:
        j = json.loads(p.read_text(encoding='utf-8'))
        cv_text = j.get('text', '') or str(j)
    except Exception:
        cv_text = p.read_text(encoding='utf-8')
else:
    cv_text = "Director of AI, Data, and Analytics\nalkashef@gmail.com | +20-100-506-2208 | Cairo"

fields = ["full_name", "first_name", "last_name", "email", "phone", "address", "alma_mater"]
for f in fields:
    try:
        out = h.generate_from_prompt_file("extract_field_user.md", prompt_vars={"cv": cv_text, "field": f}, max_new_tokens=64)
        print(f"--- FIELD: {f} ---")
        print(out)
    except Exception as e:
        print(f"ERROR for field {f}: {e}")

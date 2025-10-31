import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANON = ROOT / "tests" / "data" / "Ahmad Alkashef - Resume.json"
OPENAI = ROOT / "tests" / "data" / "Ahmad Alkashef - Resume - OpenAI.json"

with OPENAI.open('r', encoding='utf-8') as f:
    openai = json.load(f)

with CANON.open('r', encoding='utf-8') as f:
    canon = json.load(f)

# Fields to copy from openai_extraction into hermes_extraction
source = openai.get('openai_extraction', {})
copy_keys = ['full_name','first_name','last_name','email','phone','address','alma_mater']

hermes = canon.get('hermes_extraction', {})
for k in copy_keys:
    if k in source:
        hermes[k] = source[k]

canon['hermes_extraction'] = hermes

with CANON.open('w', encoding='utf-8') as f:
    json.dump(canon, f, ensure_ascii=False, indent=2)

print(f"Updated {CANON} with fields: {', '.join(copy_keys)}")

You extract fields from an English CV. Return a strict JSON object with exactly this shape:

{"full_name": "<string>"}

Rules:
- If the name is not present or cannot be determined, return {"full_name": ""}.
- Output only the JSON object. No additional text or explanation.

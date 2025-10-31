Return exactly one line containing only the value of the requested field.

Rules:
- Input CV text will be provided where the placeholder {cv} appears.
- Replace {field} with the target field name (e.g., first_name, email).
- If the field is not present, return an empty line for text fields or 0 for numeric fields.
- Do NOT include any labels, JSON, punctuation, commentary, or additional lines — only the raw value.

Formatting hints for the model loader (do NOT include these in model output):
- CV will be delimited when injected: "CV START" / "CV END".
- Keep the answer to a single short line.

Do not include any extra text or labels; return only the requested value.

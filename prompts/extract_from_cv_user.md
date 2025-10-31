Extract all requested fields from the provided CV text and return exactly one JSON object that matches the schema defined by the system message.

Instructions:
- Use only the information present in the CV text passed via the variable {cv}.
- Return a single JSON object containing only the keys specified by the system prompt.
- If a field is missing, return an empty string or 0 as appropriate for the field type.
- Output must be a valid JSON object only; do not include any surrounding commentary or markdown.

Example (for author guidance only - do NOT include in model output):
{
	"first_name": "",
	"last_name": "",
	"full_name": "",
	"email": "",
	"phone": "",
	"misspelling_count": 0,
	"misspelled_words": "",
	"visual_cleanliness": 0,
	"professional_look": 0,
	"formatting_consistency": 0,
	"years_since_graduation": 0,
	"total_years_experience": 0,
	"employer_names": "",
	"employers_count": 0,
	"avg_years_per_employer": 0,
	"years_at_current_employer": 0,
	"address": "",
	"alma_mater": "",
	"high_school": "",
	"education_system": "",
	"second_foreign_language": "",
	"flag_stem_degree": "",
	"military_service_status": "",
	"worked_at_financial_institution": "",
	"worked_for_egyptian_government": ""
}

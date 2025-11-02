import sys
import os
import time
import json
import pathlib
import warnings

# Ensure project root is on sys.path so `import utils.*` works when running
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from utils.slice import slice_sections
from utils.logger import AppLogger


def _truncate(s: str, n: int = 200) -> str:
	return s if len(s) <= n else s[: n - 3] + "..."


def load_dotenv_if_present():
	try:
		from dotenv import load_dotenv

		env_path = PROJECT_ROOT / "config" / ".env"
		if env_path.exists():
			load_dotenv(dotenv_path=str(env_path))
	except Exception:
		# dotenv not installed or failed; continue with existing env
		pass


def main() -> int:
	warnings.filterwarnings("ignore")

	load_dotenv_if_present()

	# Read env vars (with sensible defaults)
	extracted_path = os.getenv(
		"TEST_EXTRACTED_TEXT", str(PROJECT_ROOT / "tests" / "data" / "extracted_text.txt")
	)
	out_sections = os.getenv(
		"TEST_SLICED_SECTIONS", str(PROJECT_ROOT / "tests" / "data" / "sections.json")
	)

	# Initialize logger
	log_path = os.getenv("LOG_FILE_PATH", str(PROJECT_ROOT / "logs" / "test_slice.log"))
	logger = AppLogger(log_path)

	logger.log_kv("SLICE_TEST_START", extracted_path=extracted_path, out_sections=out_sections)
	print(f"[INFO] Starting slice test")
	print(f"[INFO] Extracted text input: {extracted_path}")
	print(f"[INFO] Sections output JSON: {out_sections}")

	# Read extracted text
	t0 = time.perf_counter()
	if not os.path.exists(extracted_path):
		msg = f"Extracted text file not found: {extracted_path}"
		logger.log(msg)
		print(f"[ERROR] {msg}")
		return 2

	try:
		with open(extracted_path, "r", encoding="utf-8") as fh:
			text = fh.read()
	except Exception as exc:
		logger.log_kv("SLICE_READ_FAILED", error=str(exc))
		print(f"[ERROR] Could not read extracted text: {exc}")
		return 3

	# Slice into titled sections
	print("[STEP] Slicing text into sections...")
	try:
		sections = slice_sections(text)
	except Exception as exc:
		logger.log_kv("SLICE_FAILED", error=str(exc))
		print(f"[ERROR] slice_sections failed: {exc}")
		return 4

	t1 = time.perf_counter()
	logger.log_kv("SLICE_COMPLETED", sections=len(sections), elapsed=f"{t1-t0:.2f}s")

	# Ensure output directory exists
	out_p = pathlib.Path(out_sections)
	out_p.parent.mkdir(parents=True, exist_ok=True)

	# Write JSON with pretty formatting
	try:
		with out_p.open("w", encoding="utf-8") as fh:
			json.dump(sections, fh, indent=2, ensure_ascii=False)
		print(f"[OK] Wrote {len(sections)} sections to {out_p}")
		logger.log_kv("SECTIONS_WRITTEN", path=str(out_p), count=len(sections))
	except Exception as exc:
		logger.log_kv("SECTIONS_WRITE_FAILED", error=str(exc))
		print(f"[ERROR] Could not write sections JSON: {exc}")
		return 5

	# Print a short preview
	print("\n[SECTIONS PREVIEW]")
	for i, (title, content) in enumerate(sections.items(), start=1):
		print(f"{i}. {title} (len={len(content)})\n   {_truncate(content, 200)}\n")

	print(f"[DONE] slice test complete in {t1-t0:.2f}s")
	return 0


if __name__ == "__main__":
	try:
		rc = main()
		sys.exit(rc)
	except Exception as e:
		print("Unexpected error during slice test run:", repr(e))
		sys.exit(4)


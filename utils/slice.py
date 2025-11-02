"""
Utilities to slice a long CV or job-description text into logical sections.

Public API:
- slice_text(text: str, max_section_chars: int = 2000) -> list[str]

The implementation uses a few heuristics:
- Look for header-like lines (all-caps, lines that end with ':' or common section names)
- If headers are found, split at header boundaries and attach following paragraphs
- Otherwise split on double-newlines into paragraphs and group them so sections aren't too small

This function is intentionally conservative (keeps context together) and returns a
list of cleaned section strings suitable for downstream NLP or embedding.
"""
from __future__ import annotations

from typing import List, Optional
import re


COMMON_SECTION_TOKENS = [
	"summary",
	"professional summary",
	"experience",
	"work experience",
	"education",
	"skills",
	"technical skills",
	"projects",
	"certifications",
	"achievements",
	"publications",
	"languages",
	"contact",
	"objective",
	"profile",
	"interests",
	"hobbies",
]


def _is_header_line(line: str) -> bool:
	"""Return True if the line looks like a section header.

	Heuristics applied:
	- line ends with ':'
	- line is short (<= 60 chars) and contains mostly uppercase letters or title-case
	- line matches common section tokens (case-insensitive)
	"""
	if not line:
		return False
	s = line.strip()
	if s.endswith(":"):
		return True

	# common tokens
	low = s.lower()
	for t in COMMON_SECTION_TOKENS:
		# exact token or token appears as whole word
		if low == t or re.search(rf"\b{re.escape(t)}\b", low):
			return True

	# overly short lines that are mostly uppercase or Title Case with few words
	if len(s) <= 60:
		words = s.split()
		if 1 <= len(words) <= 6:
			# percentage of uppercase letters
			letters = re.sub(r"[^A-Za-z]", "", s)
			if letters:
				up_frac = sum(1 for c in letters if c.isupper()) / len(letters)
				if up_frac > 0.5:
					return True
			# Title Case heuristic: many words start with uppercase
			title_words = sum(1 for w in words if w[:1].isupper())
			if title_words / len(words) > 0.6:
				return True

	return False


def _clean_section(s: str) -> str:
	s = s.strip()
	# collapse many blank lines
	s = re.sub(r"\n{3,}", "\n\n", s)
	# normalize spaces
	s = re.sub(r"[ \t]{2,}", " ", s)
	return s


def slice_text(text: str, *, max_section_chars: int = 2000, min_section_chars: int = 60) -> List[str]:
	"""Split `text` into a list of logical sections.

	Parameters
	- text: full CV or job description as a single string
	- max_section_chars: prefer sections no larger than this; long sections will be
	  further split on paragraph boundaries
	- min_section_chars: small sections smaller than this may be merged with neighbors

	Returns
	- list of section strings (cleaned)
	"""
	if not text:
		return []

	# normalize line endings
	text = text.replace("\r\n", "\n").replace("\r", "\n")

	lines = text.split("\n")

	# First pass: find header indices
	header_indices: List[int] = []
	for i, ln in enumerate(lines):
		if _is_header_line(ln):
			header_indices.append(i)

	sections: List[str] = []

	if header_indices:
		# Build sections starting at headers. If the document starts with text before
		# the first header, include it as a leading section.
		idxs = header_indices + [len(lines)]
		# If there's leading text before first header, include it
		first_header = header_indices[0]
		if first_header > 0:
			leading = '\n'.join(lines[:first_header]).strip()
			if leading:
				sections.append(_clean_section(leading))

		for a, b in zip(idxs[:-1], idxs[1:]):
			# include the header line and following lines up to next header
			chunk = '\n'.join(lines[a:b]).strip()
			if chunk:
				sections.append(_clean_section(chunk))

	else:
		# No headers found: split by double newlines into paragraphs and group them
		paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
		cur: List[str] = []
		cur_len = 0
		for p in paragraphs:
			plen = len(p)
			if cur and (cur_len + plen > max_section_chars):
				# flush
				sections.append(_clean_section("\n\n".join(cur)))
				cur = [p]
				cur_len = plen
			else:
				cur.append(p)
				cur_len += plen

		if cur:
			sections.append(_clean_section("\n\n".join(cur)))

	# Post-process: split overly long sections on paragraph boundaries
	final_sections: List[str] = []
	for sec in sections:
		if len(sec) <= max_section_chars:
			final_sections.append(sec)
			continue

		# split into paragraphs and make smaller groups
		paras = [p.strip() for p in re.split(r"\n\s*\n", sec) if p.strip()]
		cur = []
		cur_len = 0
		for p in paras:
			if cur and cur_len + len(p) > max_section_chars:
				final_sections.append(_clean_section("\n\n".join(cur)))
				cur = [p]
				cur_len = len(p)
			else:
				cur.append(p)
				cur_len += len(p)

		if cur:
			final_sections.append(_clean_section("\n\n".join(cur)))

	# Merge tiny neighbors (avoid singleton tiny sections)
	merged: List[str] = []
	for sec in final_sections:
		if merged and len(sec) < min_section_chars:
			merged[-1] = _clean_section(merged[-1] + "\n\n" + sec)
		else:
			merged.append(sec)

	# filter out empties
	return [s for s in merged if s.strip()]


__all__ = ["slice_text"]


def slice_sections(text: str, *, max_section_chars: int = 2000, min_section_chars: int = 60) -> dict:
	"""Return sections as a dict mapping section-title -> section-content.

	- If header-like lines are found, the header text (first line, without trailing
	  colon) is used as the section title.
	- If no headers are detected, generated titles "Section 1", "Section 2", ...
	  are used. Titles are de-duplicated by appending " (n)" when necessary.

	The function deliberately does NOT assign tokens, categories or labels to
	sections — it only returns cleaned text grouped by human-readable titles.
	"""
	sections = slice_text(text, max_section_chars=max_section_chars, min_section_chars=min_section_chars)

	# Attempt to recover titles from the original text headers. We'll parse the
	# text line-wise and look for header lines similar to the logic used in
	# _is_header_line. If the header heuristic was used when producing `sections`
	# (i.e., headers present), the first line of each section is likely the title.
	out: dict[str, str] = {}
	seen: dict[str, int] = {}

	for idx, sec in enumerate(sections, start=1):
		# candidate title is the first non-empty line up to 100 chars
		first_line = sec.splitlines()[0].strip() if sec.splitlines() else ""
		title = first_line
		if title:
			# remove trailing colon if present
			if title.endswith(":"):
				title = title[:-1].strip()
		else:
			title = f"Section {idx}"

		# if title is too long, truncate for readability
		if len(title) > 60:
			title = title[:57].rstrip() + "..."

		# ensure unique keys
		key = title
		if key in seen:
			seen[key] += 1
			key = f"{title} ({seen[title]})"
		else:
			seen[key] = 1

		out[key] = sec

	return out


# keep backward-compatibility in __all__
__all__ = ["slice_text", "slice_sections"]


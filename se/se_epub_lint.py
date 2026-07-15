#!/usr/bin/env python3
"""
The Longhouse Press fork of the SE tools package does not implement a linter (see `se.commands.lint`).

This module is kept only for the small set of shared utility classes/functions that other parts of the
toolset still depend on: `SourceFile`, `LintMessage`, `LintSubmessage`, and `files_not_in_spine()`.
"""

from bisect import bisect_right
from pathlib import Path
from typing import TYPE_CHECKING, cast

import regex

import se
from se.easy_xml import EasyXmlElement

if TYPE_CHECKING:
	from se.se_epub import SeEpub # Import under type checking guard to prevent circular import error.

NEWLINE_PATTERN = regex.compile(r"\n")

class SourceFile:
	"""
	A source file that can perform regex searches of input text that provides line
	number references to matches.
	"""

	def __init__(self, filename: Path, contents: str, bounds: list[tuple[int, int]] | None = None):
		self.filename = filename
		self.contents = contents
		self._lines = self._ensure_line_bounds(bounds)
		# For binary searching line number lookups on regex matches.
		self._offsets = [offset for (offset, _) in self._lines]

	def sub(self, pattern: str | regex.Pattern[str], replacement: str = "") -> 'SourceFile':
		"""
		Creates a modified view of the source text that retains line number mappings
		to the original text.
		"""
		if isinstance(pattern, str):
			pattern = regex.compile(pattern)

		contents, bounds = self._sub_with_line_mapping(pattern, replacement, self._lines)
		return SourceFile(self.filename, contents, bounds)

	def search(self, pattern: str | regex.Pattern[str]) -> tuple[str, int] | None:
		"""
		Search the file contents to find the first regex match, with line number.
		"""
		if isinstance(pattern, str):
			pattern = regex.compile(pattern)

		match = pattern.search(self.contents)
		if match:
			return (match.group(), self.line_num(match))

		return None

	def findall(self, pattern: str | regex.Pattern[str], flags: int = 0) -> list[tuple[str, int]]:
		"""
		Find all regex matches in the file contents, including line numbers.
		"""

		if isinstance(pattern, str):
			pattern = regex.compile(pattern, flags)

		matches: list[tuple[str, int]] = []
		for match in regex.finditer(pattern, self.contents):
			matches.append((match.group(), self.line_num(match)))

		return matches

	def find_selector(self, selector: str) -> list[tuple[str, int]]:
		"""
		If this file is a CSS file, try to find a CSS selector. If the selector can't be found, return it anyway with line number 0. The file must be pretty-printed using `se clean` for this to work well.
		"""

		# Try to find the selector using a regex.
		matches = self.findall(fr"(?<=^[ \t]*){regex.escape(selector)}(?=(::?[a-z]+)?\s*[,{{])", regex.MULTILINE)

		# In case the regex didn't match anything, include the selector anyway at line 0 which will just show an arrow in the output.
		return matches or [(selector, 0)]

	def line_num(self, match: regex.Match[str]) -> int:
		"""
		Get the original line number based on a regex match of contents.
		"""
		idx = bisect_right(self._offsets, match.start()) - 1
		return 0 if idx < 0 else self._lines[idx][1]

	def _sub_with_line_mapping(self, pattern: regex.Pattern[str], replacement: str = "", bounds: list[tuple[int, int]] | None = None) -> tuple[str, list[tuple[int, int]]]:
		"""
		Processes the contents string, replacing matched patterns while building an
		index mapping of byte offsets in the modified output to line numbers of the
		original input string.
		"""
		bounds = self._ensure_line_bounds(bounds)

		prev_idx = 0
		removed_chars = 0
		for match in pattern.finditer(self.contents):
			# Updating offsets between the prior comment and current match.
			while prev_idx < len(bounds) and bounds[prev_idx][0] <= match.start():
				entry = bounds[prev_idx]
				bounds[prev_idx] = (entry[0] - removed_chars, entry[1])
				prev_idx += 1

			removed_chars += (match.end() - match.start()) - len(replacement)

			# Delete entries for matches that span multiple lines.
			while prev_idx < len(bounds) and bounds[prev_idx][0] < match.end():
				del bounds[prev_idx]

		# Update offsets for lines after the final comment as-needed.
		if removed_chars > 0:
			while prev_idx < len(bounds):
				entry = bounds[prev_idx]
				bounds[prev_idx] = (entry[0] - removed_chars, entry[1])
				prev_idx += 1

		return (pattern.sub(replacement, self.contents), bounds)

	def _ensure_line_bounds(self, bounds: list[tuple[int, int]] | None = None) -> list[tuple[int, int]]:
		if bounds:
			return list(bounds)

		return [(0,1)] + [
			(match.start() + 1, line)
			for (line, match) in enumerate(NEWLINE_PATTERN.finditer(self.contents), 2)
		]

class LintSubmessage:
	"""
	An object representing a single instance of a lint error within a file.

	Contains the original submessage text and can be extended with additional properties like line numbers.
	"""

	def __init__(self, text: str, line_num: int | None = None, column_num: int | None = None):
		self.text = text
		self.line_num = line_num
		self.column_num = column_num

	def __str__(self) -> str:
		return self.text

	@classmethod
	def from_matches(cls, matches: list[tuple[str, int]]) -> list['LintSubmessage']:
		"""Create a list of `LintSubmessage` objects from search match tuples."""
		return [cls(match_text, line_num) for match_text, line_num in sorted(matches, key=lambda x: x[1])]

	@classmethod
	def from_nodes(cls, nodes: list[EasyXmlElement]|list[str]) -> list['LintSubmessage']:
		"""Create a list of `LintSubmessage` objects from xpath nodes. Nodes can either be element or text nodes."""
		submessages: list[LintSubmessage] = []

		for node in nodes:
			if isinstance(node, EasyXmlElement):
				submessages.append(cls(node.to_string(), node.sourceline))
			elif hasattr(node, 'getparent'):
				try:
					submessages.append(cls(node, node.getparent().sourceline)) # type: ignore # `etree` returns a special `str` with the `getparent()` method.
				except AttributeError:
					submessages.append(cls(node, 0))
			else:
				submessages.append(cls(node, 0))

		return sorted(submessages, key=lambda x: x.line_num or 0)

	@classmethod
	def from_node_tags(cls, nodes: list[EasyXmlElement]) -> list['LintSubmessage']:
		"""Create a list of `LintSubmessage` objects from xpath node tag matches."""
		return [cls(node.to_tag_string(), node.sourceline) for node in sorted(nodes, key=lambda node: node.sourceline or 0)]

	@classmethod
	def from_node_text(cls, nodes: list[EasyXmlElement]) -> list['LintSubmessage']:
		"""Create a list of `LintSubmessage` objects from xpath node text values."""
		return [cls(node.inner_text(), node.sourceline) for node in sorted(nodes, key=lambda x: x.sourceline or 0)]

class LintMessage:
	"""
	An object representing an output message for the lint function.

	Contains information like message text, severity, and the epub filename that generated the message.
	"""

	def __init__(self, code: str, text: str, message_type:int=se.MESSAGE_TYPE_WARNING, filename: Path | None = None, submessages: list[str] | set[str] | list[LintSubmessage] | None = None):
		self.code = code
		self.text = text.strip()
		self.filename = filename
		self.message_type = message_type
		self.submessages: list[LintSubmessage] | None = None

		if submessages:
			self.submessages = []
			smallest_indent = 1000
			for submessage in submessages:
				if not isinstance(submessage, LintSubmessage):
					line_num = None
					if hasattr(submessage, 'getparent'):
						line_num = submessage.getparent().sourceline # type: ignore # `etree` returns a special `str` with the `getparent()` method.
					submessage = LintSubmessage(submessage, cast(int|None, line_num)) # We have to `cast()` here because of the special `getparent()` method.
				self.submessages.append(submessage)

				# Try to flatten leading indentation.
				for indent in regex.findall(r"^\t+(?=<)", submessage.text, flags=regex.MULTILINE):
					smallest_indent = min(smallest_indent, len(indent))

			if smallest_indent == 1000:
				smallest_indent = 0

			for submessage in self.submessages:
				if smallest_indent:
					submessage.text = regex.sub(fr"^\t{{{smallest_indent}}}", "", submessage.text, flags=regex.MULTILINE)


def files_not_in_spine(self: 'SeEpub') -> set[Path]:
	"""
	Check the spine against the actual files.

	INPUTS
	None.

	OUTPUTS
	Set of files not in the spine (typically an empty set).
	"""

	xhtml_files = set(self.content_path.glob("**/*.xhtml"))
	spine_files = set(self.spine_file_paths + [self.toc_path])
	return xhtml_files.difference(spine_files)

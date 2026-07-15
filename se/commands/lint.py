"""
This module implements the `se lint` command.
"""

import argparse

import se
from se.se_help_formatter import SeHelpFormatter

def lint(plain_output: bool) -> int:
	"""
	Entry point for `se lint`.
	"""

	parser = argparse.ArgumentParser(description="Check for various Standard Ebooks style errors.", prog="[command]se[/] [subcommand]lint[/]", formatter_class=SeHelpFormatter)
	parser.add_argument("directories", metavar="[path]DIRECTORY[/]", nargs="+", help="A Standard Ebooks source directory.")
	parser.parse_args()

	exception = se.NotImplementedException("The Longhouse Press fork of the SE tools package does not implement a linter.")
	se.print_error(exception, plain_output=plain_output)

	return exception.code

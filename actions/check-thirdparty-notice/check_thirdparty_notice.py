# SPDX-FileCopyrightText: Copyright (C) 2025 Opal Health Informatics Group <https://www.opalmedapps.com>
#
# SPDX-License-Identifier: MIT

# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "beautifulsoup4==4.14.2",
#     "markdown==3.10",
#     "pip-requirements-parser==32.0.1",
#     "pyproject-metadata==0.9.1",
# ]
# ///
import argparse
import json
import sys
import tomllib
from pathlib import Path

import bs4
import markdown
from pip_requirements_parser import RequirementsFile
from pyproject_metadata import StandardMetadata


def valid_path(argument: str) -> Path:
    file = Path(argument)
    if not file.exists() or not file.is_file():
        raise ValueError(f'{argument} is not a valid file')

    return file


def is_package_name(tag: bs4.Tag) -> bool:
    # filter out accidental h2 elements when license text contains
    # a heading followed by dashes
    # which is also converted to h2
    if tag.name == 'h2':
        if tag.next_sibling and tag.next_sibling.next_sibling:
            return tag.next_sibling.next_sibling.name == 'ul'

    return False


parser = argparse.ArgumentParser()
parser.add_argument('--pyproject', metavar='pyproject-file', type=valid_path)
parser.add_argument('--pip', metavar='requirements-file', type=valid_path, nargs='+')
parser.add_argument('--npm', metavar='package-file', type=valid_path)
parser.add_argument('--composer', metavar='composer-file', type=valid_path)
parser.add_argument(
    '--additional-dependencies',
    type=str,
    nargs='+',
    default=[],
    help='Specify additional dependencies that are allowed in the third-party notice',
)

args = parser.parse_args(sys.argv[1:])

if not (args.pyproject or args.pip or args.npm or args.composer):
    raise ValueError('One of --pyproject, --pip, --npm or --composer needs to be provided')

# determine all dependencies
dependencies: set[str] = set()

if args.npm:
    package_file: Path = args.npm
    # load direct dependencies (excluding dev)
    with package_file.open() as fd:
        package_data = json.load(fd)

    for package_name in package_data['dependencies']:
        dependencies.add(package_name)

if args.composer:
    composer_file: Path = args.composer

    # load direct dependencies (excluding dev)
    with composer_file.open() as fd:
        package_data = json.load(fd)

        for package_name in package_data['require']:
            # exclude php and its extensions
            if package_name == 'php' or package_name.startswith('ext-'):
                continue

            dependencies.add(package_name)

if args.pip:
    requirements_files: list[Path] = args.pip

    for requirements_file in requirements_files:
        requirements = RequirementsFile.from_file(str(requirements_file), include_nested=True)

        for requirement in requirements.requirements:
            # some dependencies are capitalized: normalize their names
            dependencies.add(requirement.req.name.lower())

if args.pyproject:
    pyproject_file: Path = args.pyproject

    with pyproject_file.open('rb') as f:
        data = tomllib.load(f)

    metadata = StandardMetadata.from_pyproject(data)

    for dependency in metadata.dependencies:
        dependencies.add(dependency.name.lower())

    for optional_dependency in metadata.optional_dependencies.values():
        for dependency in optional_dependency:
            dependencies.add(dependency.name.lower())

# parse third-party notice by converting it to HTML and reading the level 2 headings out
with Path('THIRDPARTY.md').open() as fd:
    notice_text = fd.read()

html = markdown.markdown(notice_text)
soup = bs4.BeautifulSoup(html, 'html.parser')

dependencies_in_notice = {heading.text for heading in soup.find_all(is_package_name)}
additional_dependencies = args.additional_dependencies

for additional_dependency in additional_dependencies:
    dependencies_in_notice.remove(additional_dependency)
    print(f'Ignoring additional dependency in third-party notice: {additional_dependency}')

if dependencies != dependencies_in_notice:
    extra_in_dependencies = dependencies.difference(dependencies_in_notice)
    extra_in_notice = dependencies_in_notice.difference(dependencies)

    print('mismatch between declared dependencies in dependency files and THIRDPARTY.md found:')
    print(f'dependencies only in dependency files: {", ".join(extra_in_dependencies)}')
    print(f'dependencies only in third-party notice: {", ".join(extra_in_notice)}')

    sys.exit(1)

print('Everything is in sync!')

#!/bin/env python
import argparse
import os
import re
import yaml
import difflib
from pathlib import Path

def set_github_output(name, value):
    os.system(f'echo "{name}={value}" >> $GITHUB_OUTPUT')

def generate_and_compare_contributing(temp_path: str, charm_path: str):
    """
    Generates a contributing file from a template and compares it with an existing one.
    Sets GitHub output based on the comparison result.
    """
    TEMPLATE_FILE = Path(temp_path) / "contributing.md.template"
    INPUTS_FILE = Path(charm_path) / "contributing_inputs.yaml"
    OUTPUT_FILE = Path(temp_path) / "contributing.md"

    with open(TEMPLATE_FILE, 'r') as f:
        template = f.read()

    with open(INPUTS_FILE, 'r') as f:
        inputs_data = yaml.safe_load(f)
        keys = list(inputs_data.keys())

    for key in keys:
        value = inputs_data[key]
        print(f"Replacing {key} with {value}")
        template = template.replace(f"{{{{ {key} }}}}", value)

    with open(OUTPUT_FILE, 'w') as f:
        f.write(template)

    print("Generated contributing file from template.")

    remaining_expr = re.findall(r'{{[^}]*}}', template)
    if remaining_expr:
        print("Error: Some {{ }} expressions are still present in the generated template:")
        print("\n".join(remaining_expr))
        sys.exit(1)

    existing_file_path = Path(charm_path) / "contributing.md"
    if existing_file_path.exists():
        with open(existing_file_path, 'r') as f:
            existing_contributing_contents = f.read()
        print("Existing contributing file found")
    else:
        existing_contributing_contents = ""
        print("No existing contributing file found")

    diff = list(difflib.ndiff(existing_contributing_contents.splitlines(), template.splitlines()))
    differences = [line for line in diff if line.startswith('+ ') or line.startswith('- ')]

    if differences:
        print("Contributing file does not exist or is outdated - a PR is needed.")
        set_github_output("comparison_result", "1")
        
        print("Proposed changes: ")
        for line in diff:
            print(line)
    else:
        print("Contributing file is up to date. No need for a PR.")
        set_github_output("comparison_result", "0")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate and compare contributing files.')
    parser.add_argument('temp_path', help='The temporary path for the operation.')
    parser.add_argument('charm_path', help='The charm path in the repository.')
    args = parser.parse_args()
    generate_and_compare_contributing(args.temp_path, args.charm_path)

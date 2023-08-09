#!/bin/env python
import argparse
import os
import re
import yaml
import difflib
from pathlib import Path

def set_github_output(name, value):
    os.system(f'echo "{name}={value}" >> $GITHUB_OUTPUT')

class ResiduePlaceholdersError(Exception):    
    pass

def generate_and_compare_contributing(temp_path: str, charm_path: str):
    """
    Generates a contributing file from a template and computes the difference with an existing one.
    Returns the diff and the generated contributing contents.
    """
    TEMPLATE_FILE = Path(temp_path) / "contributing.md.template"
    INPUTS_FILE = Path(charm_path) / "contributing_inputs.yaml"

    with open(TEMPLATE_FILE, 'r') as f:
        template = f.read()

    with open(INPUTS_FILE, 'r') as f:
        inputs_data = yaml.safe_load(f)
        keys = list(inputs_data.keys())

    for key in keys:
        value = inputs_data[key]
        print(f"Replacing {key} with {value}")
        template = template.replace(f"{{{{ {key} }}}}", value)

    print("Generated contributing file from template.")

    remaining_expr = re.findall(r'{{[^}]*}}', template)
    if remaining_expr:
        err_msg = "Error: Some {{ }} expressions are still present in the generated template"
        print(f"{err_msg}:")
        print("\n".join(remaining_expr))
        raise ResiduePlaceholdersError(err_msg)

    existing_file_path = Path(charm_path) / "contributing.md"
    if existing_file_path.exists():
        with open(existing_file_path, 'r') as f:
            existing_contributing_contents = f.read()
        print("Existing contributing file found")
    else:
        existing_contributing_contents = ""
        print("No existing contributing file found")

    diff = list(difflib.ndiff(existing_contributing_contents.splitlines(), template.splitlines()))
    return diff, template

def set_comparison_result_to_github(diff):
    """
    Sets the GitHub output based on the provided diff.
    """
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
    diff, generated_contents = generate_and_compare_contributing(args.temp_path, args.charm_path)
    
    # Write the generated contributing.md file
    OUTPUT_FILE = Path(args.temp_path) / "contributing.md"
    with open(OUTPUT_FILE, 'w') as f:
        f.write(generated_contents)
    
    set_comparison_result_to_github(diff)

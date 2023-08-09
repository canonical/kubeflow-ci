import sys
import os
import re
import yaml
import difflib

def set_github_output(name, value):
    os.system(f'echo "{name}={value}" >> $GITHUB_OUTPUT')

def contains_element(element, array):
    return element in array

def main():
    # Read the temp path from the first argument
    TEMP_PATH = sys.argv[1]

    # Read the charm path from the second argument
    CHARM_PATH = sys.argv[2]

    # Define the path to the template file relative to TEMP_PATH
    TEMPLATE_FILE = os.path.join(TEMP_PATH, "contributing.md.template")

    # Define the path to the inputs file relative to the current working directory
    INPUTS_FILE = os.path.join(CHARM_PATH, "contributing_inputs.yaml")

    # Create a new file called contributing.md in the specified directory
    OUTPUT_FILE = os.path.join(TEMP_PATH, "contributing.md")

    # Read the template file contents
    with open(TEMPLATE_FILE, 'r') as f:
        template = f.read()

    # Use yaml to get the list of keys from the inputs file
    with open(INPUTS_FILE, 'r') as f:
        inputs_data = yaml.safe_load(f)
        keys = list(inputs_data.keys())

    # Iterate over the keys and extract the values using yq
    for key in keys:
        value = inputs_data[key]
        print(f"Replacing {key} with {value}")
        template = template.replace(f"{{{{ {key} }}}}", value)

    # Write the modified template to the output file
    with open(OUTPUT_FILE, 'w') as f:
        f.write(template)

    print("Generated contributing file from template.")

    # Check if there are any remaining {{ }} expressions in the generated template
    remaining_expr = re.findall(r'{{[^}]*}}', template)

    if remaining_expr:
        print("Error: Some {{ }} expressions are still present in the generated template:")
        print("\n".join(remaining_expr))
        sys.exit(1)

    # Check if contributing.md already exists in the charm path
    existing_file_path = os.path.join(CHARM_PATH, "contributing.md")
    if os.path.exists(existing_file_path):
        with open(existing_file_path, 'r') as f:
            existing_contributing_contents = f.read()
        print("Existing contributing file found")
    else:
        # If the file is not found, we treat it the same as a file with empty contents
        existing_contributing_contents = ""
        print("No existing contributing file found")

    # Generate a diff between the template and existing contents
    diff = list(difflib.ndiff(existing_contributing_contents.splitlines(), template.splitlines()))

    # Check if there are any differences
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
    main()

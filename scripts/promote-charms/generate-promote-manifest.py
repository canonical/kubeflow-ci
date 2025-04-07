import yaml
import sys

def load_yaml(file_path):
    """Load YAML data from a file."""
    with open(file_path, "r") as f:
        return yaml.safe_load(f)

def generate_promote_manifest(source_yaml, dest_yaml):
    """Generate the promotion manifest from source and destination YAMLs."""
    source_apps = source_yaml.get("applications", {})
    dest_apps = dest_yaml.get("applications", {})

    promote_data = {"applications": {}}

    for app_name, source_details in source_apps.items():
        if app_name in dest_apps:
            if "_github_dependency_repo_name" in source_details:
                continue
            promote_data["applications"][app_name] = {
                "charm": source_details["charm"],
                "source-channel": source_details["channel"],
                "destination-channel": dest_apps[app_name]["channel"]
            }

    return promote_data

def save_yaml(data, filename):
    """Save data as a YAML file."""
    with open(filename, "w") as f:
        yaml.dump(data, f, default_flow_style=False)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python script.py <source_bundle.yaml> <destination_bundle.yaml> [output.yaml]")
        sys.exit(1)

    source_file = sys.argv[1]
    dest_file = sys.argv[2]
    output_file = sys.argv[3] if len(sys.argv) > 3 else "promote-manifest.yaml"

    source_yaml = load_yaml(source_file)
    dest_yaml = load_yaml(dest_file)

    promote_manifest = generate_promote_manifest(source_yaml, dest_yaml)
    save_yaml(promote_manifest, output_file)

    print(f"Promotion manifest saved to {output_file}")

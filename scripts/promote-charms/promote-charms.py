import argparse
import subprocess
import yaml


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
                "destination-channel": dest_apps[app_name]["channel"],
            }

    return promote_data


def promote_charms(promote_manifest, dry_run=False):
    applications = promote_manifest.get("applications", {})

    if dry_run:
        print("Executing in dry run mode.")

    errors = []
    for key, values in applications.items():
        charm = values.get("charm")
        source_channel = values.get("source-channel")
        destination_channel = values.get("destination-channel")

        if source_channel and destination_channel:
            print(f"Promoting {key} from {source_channel} to {destination_channel}")
            if not dry_run:
                try:
                    subprocess.run(
                        [
                            "charmcraft",
                            "promote",
                            "--name",
                            charm,
                            "--from-channel",
                            source_channel,
                            "--to-channel",
                            destination_channel,
                            "--yes",
                        ],
                        check=True,
                    )
                except subprocess.CalledProcessError as e:
                    print(f"Error promoting {key}: {e}")
                    errors.append({key: e})

    if errors:
        print("\n##############################################\n")
        print("Execution completed with the following errors:")
        print(errors)
        print("\n##############################################\n")


def main():
    parser = argparse.ArgumentParser(description="Promote charms between channels.")
    parser.add_argument(
        "source_bundle",
        help="Path to the source bundle YAML file",
    )
    parser.add_argument(
        "destination_bundle",
        help="Path to the destination bundle YAML file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the promotion without actually executing it",
    )

    args = parser.parse_args()

    source_yaml = load_yaml(args.source_bundle)
    dest_yaml = load_yaml(args.destination_bundle)

    promote_manifest = generate_promote_manifest(source_yaml, dest_yaml)
    promote_charms(promote_manifest, args.dry_run)


if __name__ == "__main__":
    main()

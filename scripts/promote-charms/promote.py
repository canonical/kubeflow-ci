import argparse
import subprocess

import yaml


def promote_charms(yaml_file, dry_run=False):
    with open(yaml_file, "r") as f:
        data = yaml.safe_load(f)

    applications = data.get("applications", {})

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Promote charms between channels.")
    parser.add_argument("yaml_file", help="YAML file containing charm promotion details")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the promotion without actually executing it",
    )

    args = parser.parse_args()

    promote_charms(args.yaml_file, args.dry_run)

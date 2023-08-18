#!/usr/bin/python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#

"""Script to process Trivy vulnerability scans reports and produce summary."""

import argparse
import json
from pathlib import Path


def parse_json(filename):
    """Parse JSON file"""
    record_list = []
    with open(filename, "r") as json_file:
        data = json.load(json_file)

    artifact = data["ArtifactName"]
    if "OS" in data["Metadata"]:
        base = f"{data['Metadata']['OS']['Family']}:{data['Metadata']['OS']['Name']}"
    else:
        base = "N/A"

    if "Results" not in data:
        # no scan results found, skip this report
        print(f"No results in report {filename}")
        return []

    for result in data["Results"]:
        if "Vulnerabilities" not in result or len(result["Vulnerabilities"]) == 0:
            # no vulnerabilities found, skip this report
            continue
        package_type = result["Class"]
        vuln_list = result["Vulnerabilities"]
        for vuln in vuln_list:
            record_list.append(
                {
                    "artifact": artifact,
                    "base": base,
                    "class": package_type,
                    "severity": vuln["Severity"],
                }
            )

    return record_list


def main(report_path):
    input_path = Path(report_path)

    file_list = []
    if input_path.is_dir():
        # directory is supplied, retrieve list of files
        file_list = list(input_path.iterdir())
    elif input_path.is_file():
        file_list.append(input_path)
    else:
        print(f"Invalid input {report_path} supplied")
        return

    if not file_list:
        print(f"Failed to retrieve list of files from {report_path}")
        return

    for file in file_list:
        if file.suffix == ".json":
            records = parse_json(file)
        else:
            continue

        # create and output summary
        lang_pkgs = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}
        os_pkgs = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}
        for record in records:
            if record["class"] == "os-pkgs":
                os_pkgs[record["severity"]] = os_pkgs[record["severity"]] + 1
            if record["class"] == "lang-pkgs":
                lang_pkgs[record["severity"]] = lang_pkgs[record["severity"]] + 1

        print(
            f"{record['artifact']},{record['base']},{os_pkgs['CRITICAL']},{os_pkgs['HIGH']},{os_pkgs['MEDIUM']},{os_pkgs['LOW']},{lang_pkgs['CRITICAL']},{lang_pkgs['HIGH']},{lang_pkgs['MEDIUM']},{lang_pkgs['LOW']}"
        )  # noqa


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-path")
    args = parser.parse_args()
    main(args.report_path)

#!/usr/bin/python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#

"""Script to process Trivy vulnerability scans reports and send those to Jira automation"""

import json
import os
import sys
from pathlib import Path


def parse_json(filename):
    """Parse JSON file"""
    record_list = []
    with open(filename, "r") as json_file:
        data = json.load(json_file)

    artifact = data["ArtifactName"]

    if "Results" not in data:
        # no scan results found, skip this report
        print(f"No results in report {filename}")
        return []

    for result in data["Results"]:
        if "Vulnerabilities" not in result or len(result["Vulnerabilities"]) == 0:
            # no vulnerabilities found, skip this report
            continue

        vuln_list = result["Vulnerabilities"]
        for vuln in vuln_list:
            artifact = artifact.replace(":", "-")
            artifact = artifact.replace("/", "-")
            record_name = str(vuln["VulnerabilityID"] + "-" + artifact + "-" + vuln["PkgName"])
            record_result = vuln
            record_severity = vuln["Severity"]
            record_list.append(
                {
                    "name": record_name,
                    "severity": record_severity,
                    "result": record_result,
                }
            )

    return record_list


def parse_sarif(filename):
    """Parse SARIF file"""
    record_list = []
    with open(filename, "r") as json_file:
        data = json.load(json_file)
    if "runs" not in data and "tool" not in data["runs"][0]:
        # no scan results found, skip this report
        print(f"No results in report {filename}")
        return []

    rules = data["runs"][0]["tool"]["driver"]["rules"]
    results = data["runs"][0]["results"]

    for result in results:
        record_name = str(
            result["ruleId"] + "-" + os.path.basename(filename).replace(".sarif", "")
        )
        record_result = result
        record_rule = rules[result["ruleIndex"]]
        for tag in record_rule["properties"]["tags"]:
            if tag in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                record_severity = tag
        record_list.append(
            {
                "name": record_name,
                "severity": record_severity,
                "rule": record_rule,
                "result": record_result,
            }
        )

    return record_list


def main():
    input = sys.argv[1]
    input_path = Path(input)

    input_dir = ""
    file_list = []
    if input_path.is_dir():
        # directory is supplied, retrieve list of files
        file_list = os.listdir(input_path)
        input_dir = input + "/"
    elif input_path.is_file():
        file_list.append(input)

    for file in file_list:
        print(f"Processing report in: {file}")
        filename = input_dir + file
        if filename.endswith(".json"):
            records = parse_json(filename)
        elif filename.endswith(".sarif"):
            records = parse_sarif(filename)
        else:
            print(f"Unsupported file type: {file}. Skip it.")
            continue

        # send records
        for record in records:
            # send record
            print(json.dumps(record, indent=4))


#
# Start main
#
if __name__ == "__main__":
    main()

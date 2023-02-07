#!/usr/bin/python3

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
            record_name = str(artifact + " " + vuln["PkgName"] + " " + vuln["VulnerabilityID"])
            record_data = vuln
            record_list.append({"name": record_name, "data": record_data})

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
        vuln_id = result["ruleId"]
        record_name = str(os.path.basename(filename).replace(".sarif", "-") + result["ruleId"])
        record_data = rules[result["ruleIndex"]]
        record_list.append({"name": record_name, "data": record_data})

    return record_list

def main():
    input = sys.argv[1]
    input_path = Path(input)

    input_dir = ""
    FILE_LIST = []
    if input_path.is_dir():
        # directory is supplied, retrieve list of files
        FILE_LIST = os.listdir(input_path)
        input_dir = input + "/"
    elif input_path.is_file():
        FILE_LIST.append(input)

    for file in FILE_LIST:
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
            #print(f"Rec: {record['name']}, {record['data']}")
            print(f"Rec: {record['name']}")

#
# Start main
#
if __name__ == "__main__":
    main()
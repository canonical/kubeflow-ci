#!/usr/bin/python3

import json
import os
import sys
from pathlib import Path

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
    with open(filename, "r") as json_file:
        data = json.load(json_file)
    artifact = data["ArtifactName"]

    if "Results" not in data:
        # no scan results found, skip this report
        continue

    for result in data["Results"]:
        if "Vulnerabilities" not in result or len(result["Vulnerabilities"]) == 0:
            # no vulnerabilities found, skip this report
            continue

        vuln_list = result["Vulnerabilities"]
        for vuln in vuln_list:
            record_name = str(artifact + " " + vuln["PkgName"] + " " + vuln["VulnerabilityID"])
            record_data = vuln
            print(f"Send record with name: {record_name}")
            # send record

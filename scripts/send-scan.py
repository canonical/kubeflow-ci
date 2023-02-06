#!/usr/bin/python3


from pathlib import Path
import sys
import json

input = sys.argv[1]
input_path = Path(input)

FILE_LIST = []
if input_path.is_dir():
    # directory is supplied, retrieve list of files
    print("dir")
elif input_path.is_file():
    FILE_LIST.append(input)

for file in FILE_LIST:
    print(f"Processing report in: {file}")
    with open(file, "r") as json_file:
        data = json.load(json_file)
    artifact = data['ArtifactName']
    results = data['Results'][0]
    if "Vulnerabilities" not in results or len(results['Vulnerabilities']) == 0:
        # no vulnerabilities found, skip this report
        continue

    vuln_list = results['Vulnerabilities']
    for vuln in vuln_list:
        record_name = str(artifact + " " + vuln['PkgName'] + " " + vuln['VulnerabilityID'])
        record_data = vuln
        print(f"Name: {record_name}")
        # send record


        

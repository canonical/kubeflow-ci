#!/usr/bin/python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#

"""Script to process Trivy vulnerability scans reports and produce summary."""

import argparse
import json
from pathlib import Path
from typing import List


def get_reports_files_list(report_path: str) -> List[str]:
    """
    Return the list of report files to be scanned.

    If a folder is provided, then a list of all the files will be used. If only
    a single file is provided, then the output list will contain that file.
    """
    input_path = Path(report_path)

    file_list = []
    if input_path.is_dir():
        # directory is supplied, retrieve list of files
        file_list = list(input_path.iterdir())
    elif input_path.is_file():
        file_list.append(input_path)
    else:
        raise ValueError(f"Invalid input {report_path} supplied")

    if not file_list:
        raise ValueError(f"Failed to retrieve list of files for {report_path}")

    return file_list


def get_base_os(report_json: dict) -> str:
    """Return the OS base name by parsing the trivy report data."""
    base = "N/A"
    if "OS" in report_json["Metadata"]:
        base = "%s:%s" % (report_json['Metadata']['OS']['Family'],
                          report_json['Metadata']['OS']['Name'])

    return base


def get_oci_image_name(report_json: dict) -> str:
    """Return the name of the OCI Image from the trivy report data."""
    OCI_IMAGE_KEY = "ArtifactName"
    if OCI_IMAGE_KEY not in report_json:
        raise ValueError("No 'ArtifactName' key was found on the report")

    return report_json[OCI_IMAGE_KEY]


def flatten_vulnerabilities(report_json) -> List[dict]:
    """Return a list of vulnerabilites that contain severity and class."""
    if "Results" not in report_json:
        # no scan results found, skip this report
        return []

    vuln_list = []
    for result in report_json["Results"]:
        if not result.get("Vulnerabilities", 0):
            # no vulnerabilities found, skip this report
            continue

        # class is either os-pkgs or lang-pkgs
        for vuln in result["Vulnerabilities"]:
            vuln_list.append({"class": result["Class"],
                              "severity": vuln["Severity"]})

    return vuln_list


def main(report_path, print_header):
    file_list = get_reports_files_list(report_path)

    HEADER_ROW = ["IMAGE", "BASE", "CRITICAL", "HIGH", "MEDIUM", "LOW",
                  "CRITICAL-OS", "CRITICAL-LANG", "HIGH-OS", "HIGH-LANG",
                  "MEDIUM-OS", "MEDIUM-LANG", "LOW-OS", "LOW-LANG"]
    if print_header:
        print(",".join(HEADER_ROW))

    for file in file_list:
        if file.suffix != ".json":
            raise ValueError("File is not .json %s" % file)

        with open(file, "r") as json_file:
            report_json = json.load(json_file)

        oci_image = get_oci_image_name(report_json)
        base_os = get_base_os(report_json)

        # calculate total number of CVEs per category
        lang_pkgs = {"CRITICAL": 0, "HIGH": 0,
                     "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}
        os_pkgs = {"CRITICAL": 0, "HIGH": 0,
                   "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}
        all_pkgs = {"CRITICAL": 0, "HIGH": 0,
                    "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}

        for vulnerability in flatten_vulnerabilities(report_json):
            clss = vulnerability["class"]
            sev = vulnerability["severity"]

            all_pkgs[sev] += 1
            if clss == "os-pkgs":
                os_pkgs[sev] += 1
            if clss == "lang-pkgs":
                lang_pkgs[sev] += 1

        base_info = "%s,%s" % (oci_image, base_os)
        all_pkgs_info = "%s,%s,%s,%s" % (all_pkgs['CRITICAL'],
                                         all_pkgs['HIGH'],
                                         all_pkgs['MEDIUM'], all_pkgs['LOW'])
        crit_info = "%s,%s" % (os_pkgs['CRITICAL'], lang_pkgs['CRITICAL'])
        high_info = "%s,%s" % (os_pkgs['HIGH'], lang_pkgs['HIGH'])
        medium_info = "%s,%s" % (os_pkgs['MEDIUM'], lang_pkgs['MEDIUM'])
        low_info = "%s,%s" % (os_pkgs['LOW'], lang_pkgs['LOW'])

        print("%s,%s,%s,%s,%s,%s" % (base_info, all_pkgs_info, crit_info,
                                     high_info, medium_info, low_info))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-path")
    parser.add_argument("--print-header", action="store_true")
    args = parser.parse_args()
    main(args.report_path, args.print_header)

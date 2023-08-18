#!/bin/bash
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Scan all images for vulnerabilities
#
# Usage: scan.sh <file>
#

FILE=$1
TRIVY_REPORTS_DIR="trivy-reports"
TRIVY_REPORT_TYPE="json"

if [ -d "$TRIVY_REPORTS_DIR" ]; then
    echo "WARNING: $TRIVY_REPORTS_DIR directory already exists. Some reports might not be generated."
    echo "         To scan all images remove $TRIVY_REPORTS_DIR directory."
fi

echo "Scan container images specified in $FILE"
DATE=$(date +%F)
SCAN_SUMMARY_FILE="scan-summary.csv"
if [ ! -f $SCAN_SUMMARY_FILE ]; then
    # create header for scan summary file, if it does not exist
    echo "IMAGE,BASE,CRITICAL,HIGH,MEDIUM,LOW,CRITICAL-OS,CRITICAL-LANG,HIGH-OS,HIGH-LANG,MEDIUM-OS,MEDIUM-LANG,LOW-OS,LOW-LANG" >> $SCAN_SUMMARY_FILE
fi

# create directory for trivy reports
mkdir -p "$TRIVY_REPORTS_DIR"

readarray -t IMAGE_LIST < $FILE

# for every image generate trivy report and store it in `$TRIVY_REPORTS_DIR/` directory
# '.', ':' and '/' in image names are replaced with '-' for files
for IMAGE in "${IMAGE_LIST[@]}"; do
    # trivy report name should contain artifact name being scanned with where '.', ':' and '/' replaced with '-'
    TRIVY_REPORT="$IMAGE"
    TRIVY_REPORT=$(echo $TRIVY_REPORT | sed 's/:/-/g')
    TRIVY_REPORT=$(echo $TRIVY_REPORT | sed 's/\//-/g')
    TRIVY_REPORT=$(echo $TRIVY_REPORT | sed 's/\./-/g')
    TRIVY_REPORT=$(echo "$TRIVY_REPORTS_DIR/$TRIVY_REPORT.$TRIVY_REPORT_TYPE")
    if [ -f "$TRIVY_REPORT" ]; then
      echo "Trivy report '$TRIVY_REPORT' for $IMAGE already exist, skip it"
      continue
    fi
    echo "Scan image $IMAGE report in $TRIVY_REPORT"
    docker pull $IMAGE
    docker run -v /var/run/docker.sock:/var/run/docker.sock -v `pwd`:`pwd` -w `pwd` --name=scanner aquasec/trivy image --timeout 30m -f $TRIVY_REPORT_TYPE -o $TRIVY_REPORT --ignore-unfixed $IMAGE
    if [ "$TRIVY_REPORT_TYPE" = "json" ]; then
      # for JSON type retrieve severity counts
      get-summary.py --report-path $TRIVY_REPORT >> $SCAN_SUMMARY_FILE
    fi
    docker rmi $IMAGE
    docker rm -f $(docker ps -a -q)
    df . -h
done

cat $SCAN_SUMMARY_FILE

# Use script's own repo as reference for copying over files
SCRIPTPATH="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"

rm .github/ISSUE_TEMPLATE/bug_report.yml
cp -a $SCRIPTPATH/files/. .

# Dumps logs relevant to kubernetes-based Juju charms
# Developed for dumping logs from GH Workflows, but useful for other places too
# 
# Logs are both printed to screen and dumped in the OUTPUT_DIR (default: tmp)
#
# Prerequisites:
# * juju crashdump (`snap install juju-crashdump`)
# * kubectl (with a kube config for the relevant cluster)
# * ketall (https://github.com/corneliusweig/ketall)
#
# Warning: This dumps a lot of details from your kubernetes cluster and juju models.
# Before sending this information to anyone, you should inspect it to ensure no
# sensitive information is being shared.


# Inputs
OUTPUT_DIR=${OUTPUT_DIR:-tmp}
# Defaults to the location on a gh runner
CHARMCRAFT_LOG_DIR=${CHARMCRAFT_LOG_DIR:-"/home/runner/snap/charmcraft/common/cache/charmcraft/log"}

echo "Dumping logs to ${OUTPUT_DIR}"

############
# Charmcraft

# Collect charmcraft log files, if they exist
for f in `ls $CHARMCRAFT_LOG_DIR/charmcraft-*.log`; do
    echo cat $f | tee $OUTPUT_DIR/`basename $f`
    cat $f | tee "$OUTPUT_DIR/`basename $f`"
done

############
# Juju

# Collect juju-crashdump
juju-crashdump -o "$OUTPUT_DIR"

# Collect `juju show-status-log` for every model, unit, and application
# Expand $model and $unit with a substitution that replaces '/' with '-'
for model in `juju list-models --format yaml | yq e '.models[].name'`; do
    echo juju show-status-log --days 1 --type model $model | tee "$OUTPUT_DIR/juju-status-logs-model-${model//\//-}.txt"
    juju show-status-log --days 1 --type model $model | tee "$OUTPUT_DIR/juju-status-logs-model-${model//\//-}.txt"

	for application in `juju status -m $model --format yaml | yq e '.applications | keys | .[]'`; do
		echo juju show-status-log --days 1 --type application $application | tee "$OUTPUT_DIR/juju-status-logs-application-$application.txt"
		juju show-status-log --days 1 --type application $application | tee "$OUTPUT_DIR/juju-status-logs-application-$application.txt"
	done
	for unit in `juju status -m $model --format yaml | yq e '.applications[].units | keys | .[]'`; do
        echo juju show-status-log --days 1 --type unit $unit | tee "$OUTPUT_DIR/juju-status-logs-unit-${unit//\//-}.txt"
        juju show-status-log --days 1 --type unit $unit | tee "$OUTPUT_DIR/juju-status-logs-unit-${unit//\//-}.txt"
	done
done	

############
# Kubernetes

kubectl cluster-info dump | tee "$OUTPUT_DIR/kubectl-cluster-info-dump.txt"

# Deeper resource details and logs
ketall | tee "$OUTPUT_DIR/kubernetes-ketall.txt"
ketall -o yaml | tee "$OUTPUT_DIR/kubernetes-ketall-detailed.yaml"

# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
"""Helper for shelling out to the Juju CLI"""

from subprocess import PIPE, Popen

from ruamel.yaml import YAML


class Juju:
    """Helpers to interact with the Juju CLI"""

    @staticmethod
    def juju(*args, raise_on_stderr: bool = False):
        """Executes `juju`"""
        cmd = ["juju"] + list(args)
        proc = Popen(cmd, stdout=PIPE, stderr=PIPE)
        stdout = proc.stdout.read().decode("utf-8")
        stderr = proc.stderr.read().decode("utf-8")
        if raise_on_stderr and stderr:
            raise ValueError(
                f"failed to run juju command successfully.  Got this from stderr: {stderr}"
            )
        return stdout, stderr

    @classmethod
    def info(cls, charm_name: str):
        """Convenience function for `juju info`"""
        stdout, stderr = cls.juju("info", charm_name, "--format", "yaml", raise_on_stderr=False)
        failure_message = "Failed to load valid yaml from `juju info`"
        try:
            yaml = YAML(typ="rt")
            data_dict = yaml.load(stdout)
        except Exception:  # TODO: This should be more specific
            raise JujuFailedError(failure_message, stderr=stderr, stdout=stdout)

        if not data_dict:
            raise JujuFailedError(failure_message, stderr=stderr, stdout=stdout)

        return data_dict


class JujuFailedError(Exception):
    """Error raised when calls to the Juju CLI fail.  Includes stderr and stdout of the call."""

    def __init__(self, msg: str, stderr: str, stdout: str):
        super().__init__(str(msg))
        self.stderr = stderr
        self.stdout = stdout

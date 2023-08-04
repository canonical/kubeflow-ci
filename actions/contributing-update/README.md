### Contributing Workflow

This action checks the contributing file for a charm and updates it if necessary. The action runs a script that generates a fresh contributing file from a template and placeholder values defined at the charm level. This generated file is compared against the contributing file already in the charm's directory. If they differ, another step is run to create a PR overwriting the existing file with the freshly generated one.

### contributing_inputs.yaml

This file, existing in charm's directory, defines all charm-specific inputs that will be injected into the `contributing.md.template` file to form the new `contributing.md` file. If this file doesn't exist, or doesn't contain definitions for all template values, the contributing update will fail, as there won't be enough information to generate the new `contributing.md` file from the template.
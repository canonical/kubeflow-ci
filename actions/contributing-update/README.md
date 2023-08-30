## Contributing Workflow

This action checks the contributing file for a charm and updates it if necessary. The action runs a script that generates a fresh contributing file from a template and placeholder values defined at the charm level. This generated file is compared against the contributing file already in the charm's directory. If they differ, another step is run to create a PR overwriting the existing file with the freshly generated one.

## contributing_inputs.yaml

This file, existing in charm's directory, defines all charm-specific inputs that will be injected into the `contributing.md.template` file to form the new `contributing.md` file. If this file doesn't exist, or doesn't contain definitions for all template values, the contributing update will fail, as there won't be enough information to generate the new `contributing.md` file from the template.

## Updates

### Charm Specific

Whenever we want to make changes to a charm contributing.md, we:

1. Update `contributing_inputs.yaml`
1. We can also update the `contributing.md` file directly if we like, if we want to avoid another PR
1. Push our changes
1. If the freshly generated `contributing.md`, based on the updated `contributing_inputs.yaml` plus the `contributing.md.template`, differs from `contributing.md`, the automation will catch this, and a PR will be opened to overwrite the existing `contributing.md` with the new one.

Note: the generate PR will target the `main` branch, BUT the target branch could always be changed to the same branch as the one updating `contributing_inputs.yaml`, and then merged into that without review, to avoid having two PRs to review.

### Template Updates

Even if the charm-specific `contributing_inputs.yaml` has not changed, it is possible that `contributing.md.template` will change over time. In this case, all repositories using this workflow should re-run it. It is advisable, therefore, for such repositories to ensure they are running this workflow on a regular schedule, e.g. weekly, to detect such updates.

# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Command-line entrypoint for the bump-rock workflow.

Each stage from the spec (parse, validate-urls, fetch) is exposed as a
sub-command so that it can be exercised independently while developing
locally, without burning LLM tokens or touching GitHub.

Examples:
    bump-rock parse ~/code/kserve-rocks/pmmlserver
    bump-rock validate-urls ~/code/kserve-rocks/pmmlserver --target-version 0.18.0
    bump-rock fetch ~/code/kserve-rocks/pmmlserver --target-version 0.18.0 \
        --out tmp/
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Tuple

import requests

from . import fetch as fetch_mod
from . import generate as generate_mod
from . import git_ops as git_ops_mod
from . import llm as llm_mod
from . import pr as pr_mod
from . import repair as repair_mod
from . import rockcraft
from . import run as run_mod
from .errors import BumpRockError
from .urls import UpstreamRef, parse_all


def _github_token_from_env() -> str | None:
    """Return a GitHub token from the environment for API authentication."""
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("ROCKS_REPO_TOKEN")


def _print_json(payload) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def cmd_parse(args: argparse.Namespace) -> int:
    """Implement `bump-rock parse <rock_dir>`."""
    doc = rockcraft.load(Path(args.rock_dir))
    refs = parse_all(doc.based_on_urls)
    _print_json(
        {
            "rockcraft_yaml": str(doc.path),
            "name": doc.name,
            "version": doc.version,
            "based_on": [
                {
                    "url": r.blob_url(),
                    "org": r.org,
                    "repo": r.repo,
                    "ref": r.ref,
                    "path": r.path,
                }
                for r in refs
            ],
        }
    )
    return 0


def cmd_validate_urls(args: argparse.Namespace) -> int:
    """Implement `bump-rock validate-urls <rock_dir> --target-version X`."""
    doc = rockcraft.load(Path(args.rock_dir))
    old_refs = parse_all(doc.based_on_urls)

    session = requests.Session()
    token = _github_token_from_env()
    timeout = args.timeout

    results = []
    overall_ok = True
    for old_ref in old_refs:
        new_ref = old_ref.with_ref(args.target_version)
        old_res = repair_mod.validate_or_repair(
            old_ref, session, timeout=timeout, token=token
        )
        new_res = repair_mod.validate_or_repair(
            new_ref, session, timeout=timeout, token=token
        )
        if not (old_res.ok and new_res.ok):
            overall_ok = False
        results.append(
            {
                "old": _validation_payload(old_res),
                "new": _validation_payload(new_res),
            }
        )

    _print_json({"ok": overall_ok, "urls": results})
    return 0 if overall_ok else 1


def _validation_payload(result: repair_mod.ValidationResult) -> dict:
    payload: dict = {
        "url": result.ref.blob_url(),
        "ok": result.ok,
    }
    if result.was_repaired and result.repaired_from is not None:
        payload["repaired_from"] = result.repaired_from.blob_url()
    if result.candidates:
        payload["candidates"] = [c.blob_url() for c in result.candidates]
    if result.error:
        payload["error"] = result.error
    return payload


def cmd_fetch(args: argparse.Namespace) -> int:
    """Implement `bump-rock fetch <rock_dir> --target-version X --out DIR`."""
    doc = rockcraft.load(Path(args.rock_dir))
    old_refs = parse_all(doc.based_on_urls)

    session = requests.Session()
    token = _github_token_from_env()
    out_dir = Path(args.out)

    written: List[dict] = []
    resolved_pairs = _resolve_pairs(old_refs, args.target_version, session, args.timeout, token)
    for old_res, new_res in resolved_pairs:
        pair = fetch_mod.fetch_pair(old_res.ref, new_res.ref, session, timeout=args.timeout)
        paths = fetch_mod.write_pair_to_disk(pair, out_dir)
        written.append(
            {
                "old_url": old_res.ref.blob_url(),
                "new_url": new_res.ref.blob_url(),
                "old_path": str(paths["old"]),
                "new_path": str(paths["new"]),
            }
        )

    _print_json({"out": str(out_dir), "files": written})
    return 0


def _resolve_pairs(
    old_refs: List[UpstreamRef],
    target_version: str,
    session: requests.Session,
    timeout: int,
    token: str | None,
) -> List[Tuple[repair_mod.ValidationResult, repair_mod.ValidationResult]]:
    """Validate-or-repair both old and new refs for each parsed URL.

    Returns the per-URL pair of `ValidationResult`s so callers can inspect
    whether either side was repaired (for the PR body's Reviewer follow-ups
    section) without re-running the validation.

    Raises BumpRockError if any ref cannot be resolved into a single, working
    URL — the caller surfaces that as a non-zero exit.
    """
    resolved: List[Tuple[repair_mod.ValidationResult, repair_mod.ValidationResult]] = []
    for old_ref in old_refs:
        new_ref_target = old_ref.with_ref(target_version)
        old_res = repair_mod.validate_or_repair(
            old_ref, session, timeout=timeout, token=token
        )
        new_res = repair_mod.validate_or_repair(
            new_ref_target, session, timeout=timeout, token=token
        )
        if not old_res.ok:
            raise BumpRockError(
                f"cannot resolve old upstream URL {old_ref.blob_url()}: {old_res.error}"
            )
        if not new_res.ok:
            raise BumpRockError(
                f"cannot resolve new upstream URL {new_ref_target.blob_url()}: "
                f"{new_res.error}"
            )
        resolved.append((old_res, new_res))
    return resolved


def cmd_generate(args: argparse.Namespace) -> int:
    """Implement `bump-rock generate <rock_dir> --target-version X --out DIR`.

    Runs the full pre-PR pipeline: parse, validate-or-repair, fetch, LLM
    generate (with the §6.6 validators and capped retries), then writes
    both the proposed rockcraft.yaml and debug artifacts to `--out`.
    """
    doc = rockcraft.load(Path(args.rock_dir))
    old_refs = parse_all(doc.based_on_urls)

    session = requests.Session()
    token = _github_token_from_env()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    resolved_pairs = _resolve_pairs(
        old_refs, args.target_version, session, args.timeout, token
    )
    fetched: List[fetch_mod.DockerfilePair] = []
    for old_res, new_res in resolved_pairs:
        pair = fetch_mod.fetch_pair(old_res.ref, new_res.ref, session, timeout=args.timeout)
        fetch_mod.write_pair_to_disk(pair, out_dir)
        fetched.append(pair)

    client = llm_mod.build_client(args.llm, args.model)
    result = generate_mod.generate(
        client=client,
        doc=doc,
        pairs=fetched,
        target_version=args.target_version,
        max_retries=args.max_retries,
    )

    out_path = out_dir / "rockcraft.yaml.new"
    out_path.write_text(result.rockcraft_yaml)

    debug_path = out_dir / "llm_raw_responses.txt"
    with debug_path.open("w") as fp:
        for i, raw in enumerate(result.raw_responses, start=1):
            fp.write(f"=== attempt {i} ===\n{raw}\n\n")

    _print_json(
        {
            "rockcraft_yaml_new": str(out_path),
            "attempts": result.attempts,
            "model": args.model or llm_mod.DEFAULT_OPENROUTER_MODEL,
            "llm_provider": args.llm,
            "raw_responses_log": str(debug_path),
        }
    )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Implement `bump-rock run <rock_dir> --target-version X --out DIR`.

    Full pre-PR pipeline per spec §6.6+§6.7: parse, validate-or-repair,
    fetch, then generate-+-sanity-test with capped retry. Operates on a
    copy of the rock folder under `<out>/work/` so the user's source tree
    is never touched.
    """
    rock_dir = Path(args.rock_dir)
    doc = rockcraft.load(rock_dir)
    old_refs = parse_all(doc.based_on_urls)

    session = requests.Session()
    token = _github_token_from_env()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    resolved_pairs = _resolve_pairs(
        old_refs, args.target_version, session, args.timeout, token
    )
    fetched: List[fetch_mod.DockerfilePair] = []
    for old_res, new_res in resolved_pairs:
        pair = fetch_mod.fetch_pair(old_res.ref, new_res.ref, session, timeout=args.timeout)
        fetch_mod.write_pair_to_disk(pair, out_dir)
        fetched.append(pair)

    work_dir = out_dir / "work"
    run_mod.prepare_work_dir(rock_dir, work_dir)

    client = llm_mod.build_client(args.llm, args.model)
    result = run_mod.run(
        client=client,
        doc=doc,
        pairs=fetched,
        target_version=args.target_version,
        work_dir=work_dir,
        max_sanity_attempts=args.max_sanity_attempts,
        max_llm_retries=args.max_retries,
        skip_tox=args.skip_tox,
    )

    _write_attempt_artifacts(out_dir, result)

    if not result.ok:
        _print_json(
            {
                "ok": False,
                "attempts": len(result.attempts),
                "error": result.final_error,
                "work_dir": str(work_dir),
                "attempts_log_dir": str(out_dir / "attempts"),
            }
        )
        return 1

    final_path = out_dir / "rockcraft.yaml.new"
    final_path.write_text(result.final_rockcraft_yaml or "")

    # Defence in depth: confirm only rockcraft.yaml changed in work_dir.
    try:
        run_mod.assert_only_rockcraft_changed(rock_dir, work_dir)
    except BumpRockError as exc:
        _print_json(
            {
                "ok": False,
                "attempts": len(result.attempts),
                "error": f"single-file constraint violated: {exc}",
                "work_dir": str(work_dir),
            }
        )
        return 1

    sanity_envs = (
        []
        if args.skip_tox
        else [tr.env for tr in result.attempts[-1].test_results if tr.ok]
    )
    metadata = pr_mod.build_metadata(
        rock_name=rock_dir.name,
        old_version=doc.version,
        target_version=args.target_version,
        resolved_pairs=resolved_pairs,
        model=args.model or llm_mod.DEFAULT_OPENROUTER_MODEL,
        attempts=len(result.attempts),
        sanity_envs_run=sanity_envs,
        skip_tox=args.skip_tox,
    )
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    _print_json(
        {
            "ok": True,
            "attempts": len(result.attempts),
            "rockcraft_yaml_new": str(final_path),
            "metadata": str(out_dir / "metadata.json"),
            "work_dir": str(work_dir),
            "attempts_log_dir": str(out_dir / "attempts"),
        }
    )
    return 0


def _write_attempt_artifacts(out_dir: Path, result: run_mod.RunResult) -> None:
    """Persist a folder per attempt so failures can be inspected later."""
    attempts_dir = out_dir / "attempts"
    attempts_dir.mkdir(exist_ok=True)
    for outcome in result.attempts:
        adir = attempts_dir / f"attempt-{outcome.attempt}"
        adir.mkdir(exist_ok=True)
        (adir / "rockcraft.yaml").write_text(outcome.rockcraft_yaml)
        for tr in outcome.test_results:
            (adir / f"tox-{tr.env}.log").write_text(tr.log_tail)


def cmd_open_pr(args: argparse.Namespace) -> int:
    """Implement `bump-rock open-pr <target_repo> --out-dir DIR [--confirm]`.

    Reads `<out-dir>/metadata.json` + `<out-dir>/rockcraft.yaml.new` from a
    previous `bump-rock run` invocation, plans the branch + commit + PR
    body, and (only with `--confirm`) actually pushes the branch and opens
    the PR. Without `--confirm`, prints the full plan as JSON for review.
    """
    target_repo = Path(args.target_repo)
    out_dir = Path(args.out_dir)
    metadata_path = out_dir / "metadata.json"
    new_yaml_path = out_dir / "rockcraft.yaml.new"

    if not metadata_path.is_file():
        raise BumpRockError(f"metadata file not found: {metadata_path}")
    if not new_yaml_path.is_file():
        raise BumpRockError(f"generated rockcraft.yaml not found: {new_yaml_path}")
    if not (target_repo / ".git").is_dir():
        raise BumpRockError(f"target repo not a git checkout: {target_repo}")

    metadata = json.loads(metadata_path.read_text())
    rock_name = metadata["rock_name"]
    target_version = metadata["target_version"]
    new_yaml = new_yaml_path.read_text()

    rock_subdir = target_repo / rock_name
    if not (rock_subdir / "rockcraft.yaml").is_file():
        raise BumpRockError(
            f"rock folder not found in target repo: {rock_subdir} "
            "(does the target repo have this rock?)"
        )

    base_branch = pr_mod.branch_name(rock_name, target_version)
    commit_msg = pr_mod.commit_message(rock_name, target_version)
    title = pr_mod.pr_title(rock_name, target_version)
    body = pr_mod.pr_body(metadata)

    plan = {
        "target_repo": str(target_repo),
        "rock_name": rock_name,
        "target_version": target_version,
        "branch": base_branch,
        "commit_message": commit_msg,
        "pr_title": title,
        "pr_body_preview": body,
        "label": pr_mod.LABEL_AI_GENERATED,
    }

    if not args.confirm:
        plan["dry_run"] = True
        plan["note"] = (
            "Dry run. Re-run with --confirm to push and open the PR. "
            "Nothing was written to the target repo."
        )
        _print_json(plan)
        return 0

    git_ops_mod.assert_clean_main(target_repo)
    existing = git_ops_mod.remote_branches(target_repo)
    branch = pr_mod.branch_name_with_suffix(rock_name, target_version, existing)

    # Stage the change: overwrite the rock's rockcraft.yaml.
    (rock_subdir / "rockcraft.yaml").write_text(new_yaml)

    git_ops_mod.create_commit_push(
        target_repo,
        branch=branch,
        file_to_stage=f"{rock_name}/rockcraft.yaml",
        commit_message=commit_msg,
    )
    pr_url = git_ops_mod.create_pr(
        target_repo,
        title=title,
        body=body,
        label=pr_mod.LABEL_AI_GENERATED,
    )

    _print_json(
        {
            "ok": True,
            "branch": branch,
            "pr_url": pr_url,
            "rock_name": rock_name,
            "target_version": target_version,
        }
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argparse parser."""
    parser = argparse.ArgumentParser(
        prog="bump-rock",
        description="Helpers for the rock-version-bump GitHub workflow.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_parse = sub.add_parser("parse", help="Parse a rock folder's rockcraft.yaml.")
    p_parse.add_argument("rock_dir", help="Path to the rock folder.")
    p_parse.set_defaults(func=cmd_parse)

    p_val = sub.add_parser(
        "validate-urls",
        help="Validate (and repair) old + new # Based on URLs for a target version.",
    )
    p_val.add_argument("rock_dir", help="Path to the rock folder.")
    p_val.add_argument("--target-version", required=True, help="New upstream version.")
    p_val.add_argument("--timeout", type=int, default=30, help="HTTP timeout (s).")
    p_val.set_defaults(func=cmd_validate_urls)

    p_fetch = sub.add_parser(
        "fetch",
        help="Fetch old + new Dockerfiles into a local directory.",
    )
    p_fetch.add_argument("rock_dir", help="Path to the rock folder.")
    p_fetch.add_argument("--target-version", required=True, help="New upstream version.")
    p_fetch.add_argument("--out", required=True, help="Output directory.")
    p_fetch.add_argument("--timeout", type=int, default=30, help="HTTP timeout (s).")
    p_fetch.set_defaults(func=cmd_fetch)

    p_gen = sub.add_parser(
        "generate",
        help="Call the LLM to produce an updated rockcraft.yaml.",
    )
    p_gen.add_argument("rock_dir", help="Path to the rock folder.")
    p_gen.add_argument("--target-version", required=True, help="New upstream version.")
    p_gen.add_argument("--out", required=True, help="Output directory.")
    p_gen.add_argument(
        "--llm",
        default="openrouter",
        choices=["openrouter", "mock"],
        help="LLM provider (default: openrouter).",
    )
    p_gen.add_argument(
        "--model",
        default=None,
        help="Model id override (default: provider-specific).",
    )
    p_gen.add_argument(
        "--max-retries",
        type=int,
        default=generate_mod.MAX_LLM_RETRIES,
        help="Additional attempts after the first if validation fails.",
    )
    p_gen.add_argument("--timeout", type=int, default=30, help="HTTP timeout (s).")
    p_gen.set_defaults(func=cmd_generate)

    p_run = sub.add_parser(
        "run",
        help="Full pre-PR pipeline: generate + sanity tests with capped retry.",
    )
    p_run.add_argument("rock_dir", help="Path to the rock folder.")
    p_run.add_argument("--target-version", required=True, help="New upstream version.")
    p_run.add_argument("--out", required=True, help="Output directory.")
    p_run.add_argument(
        "--llm",
        default="openrouter",
        choices=["openrouter", "mock"],
        help="LLM provider (default: openrouter).",
    )
    p_run.add_argument("--model", default=None, help="Model id override.")
    p_run.add_argument(
        "--max-retries",
        type=int,
        default=generate_mod.MAX_LLM_RETRIES,
        help="Inner LLM retries per generate call.",
    )
    p_run.add_argument(
        "--max-sanity-attempts",
        type=int,
        default=run_mod.MAX_SANITY_ATTEMPTS,
        help="Outer attempts before giving up (each = generate + tox).",
    )
    p_run.add_argument(
        "--skip-tox",
        action="store_true",
        help="Skip the tox sanity pipeline (local prompt iteration only).",
    )
    p_run.add_argument("--timeout", type=int, default=30, help="HTTP timeout (s).")
    p_run.set_defaults(func=cmd_run)

    p_pr = sub.add_parser(
        "open-pr",
        help="Apply the generated rockcraft.yaml to a target repo and open a PR.",
    )
    p_pr.add_argument(
        "target_repo",
        help="Path to a local clone of the target rocks repo (must be on main).",
    )
    p_pr.add_argument(
        "--out-dir",
        required=True,
        help="Output directory from a prior `bump-rock run` (must contain "
        "metadata.json and rockcraft.yaml.new).",
    )
    p_pr.add_argument(
        "--confirm",
        action="store_true",
        help="Actually push the branch and open the PR. Without this flag, "
        "the command runs in dry-run mode and prints the plan.",
    )
    p_pr.set_defaults(func=cmd_open_pr)

    return parser


def main(argv: List[str] | None = None) -> int:
    """Console entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except BumpRockError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

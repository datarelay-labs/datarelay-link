#!/usr/bin/env python3
"""Regression coverage for the provenance-commit release-attest binding."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-release-attest-binding.py"
QUALIFICATION_SCRIPT = ROOT / "scripts" / "check-release-qualification-evidence.py"


def load_checker():
    spec = importlib.util.spec_from_file_location("check_release_attest_binding", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load %s" % SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = load_checker()

GIT_ENV = os.environ.copy()
GIT_ENV.update(
    {
        "GIT_AUTHOR_NAME": "binding-test",
        "GIT_AUTHOR_EMAIL": "binding-test@example.com",
        "GIT_COMMITTER_NAME": "binding-test",
        "GIT_COMMITTER_EMAIL": "binding-test@example.com",
    }
)


def fail(message: str) -> None:
    print("FAIL %s" % message, file=sys.stderr)
    raise SystemExit(1)


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=GIT_ENV,
    )
    return proc.stdout.strip()


def write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def manifest(channel: str, git_ref: str, source_head: str, version: str = "1.2.3") -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "project_version": version,
            "frp_version": "0.71.0",
            "channel": channel,
            "git_ref": git_ref,
            "source_head": source_head,
            "immutable_source_ref": git_ref,
            "features": {"mcp_included": True},
            "artifacts": {
                "bootstrap-client.sh": {
                    "path": "dist/bootstrap-client.sh",
                    "sha256": "a" * 64,
                }
            },
        },
        indent=2,
    ) + "\n"


def init_repo(repo: Path, channel: str = "development") -> None:
    git(repo, "init", "-b", "main")
    write(
        repo,
        "VERSION",
        "PROJECT_VERSION=1.2.3\nFRP_VERSION=0.71.0\nRELEASE_CHANNEL=%s\n" % channel,
    )
    write(repo, "lib/product.sh", "echo product\n")
    write(repo, "release-manifest.json", manifest(channel, "0" * 40, "0" * 40))
    write(repo, "dist/bootstrap-client.sh", "echo bootstrap-v0\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "content")


def stamp(
    repo: Path,
    channel: str,
    git_ref: str,
    source_head: str,
    version: str = "1.2.3",
) -> str:
    write(repo, "release-manifest.json", manifest(channel, git_ref, source_head, version=version))
    write(repo, "dist/bootstrap-client.sh", "echo bootstrap-%s\n" % source_head[:12])
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "provenance")
    return git(repo, "rev-parse", "HEAD")


def run_cli(
    repo: Path,
    input_ref: str,
    workflow_ref: str,
    workflow_sha: str,
    qualified_head: str = "",
) -> subprocess.CompletedProcess[str]:
    env = GIT_ENV.copy()
    env.update(
        {
            "INPUT_REF": input_ref,
            "WORKFLOW_REF": workflow_ref,
            "WORKFLOW_SHA": workflow_sha,
        }
    )
    if qualified_head:
        env.update(
            {
                "QUALIFICATION_PASS1_HEAD": qualified_head,
                "QUALIFICATION_PASS2_HEAD": qualified_head,
                "QUALIFICATION_FINAL_HEAD": qualified_head,
                "QUALIFICATION_EVIDENCE_SHA256": "e" * 64,
                "QUALIFICATION_TRUSTED_REVIEW": "PASS",
                "QUALIFICATION_TRUSTED_REVIEW_SHA256": "e" * 64,
            }
        )
    if qualified_head and input_ref == "v2.4.0":
        env.update(
            {
                "QUALIFICATION_CHATGPT_OWNER_UI_ACCEPTANCE": "PASS",
                "QUALIFICATION_CHATGPT_OWNER_EVIDENCE_SHA256": "d" * 64,
                "QUALIFICATION_CHATGPT_OWNER_EVIDENCE_PROVENANCE_HEAD": qualified_head,
                "QUALIFICATION_TRUSTED_OWNER_UI_REVIEW": "PASS",
                "QUALIFICATION_TRUSTED_OWNER_UI_REVIEW_SHA256": "d" * 64,
            }
        )
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(repo)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def assert_fail(proc: subprocess.CompletedProcess[str], needle: str) -> None:
    if proc.returncode == 0:
        fail("expected failure containing %r, stdout=%s" % (needle, proc.stdout))
    if needle not in proc.stderr:
        fail("stderr missing %r: %s" % (needle, proc.stderr))


def test_workflow_uses_checker() -> None:
    text = (ROOT / ".github/workflows/release-attest.yml").read_text(encoding="utf-8")
    if "scripts/check-release-attest-binding.py" not in text:
        fail("release-attest.yml does not call the binding checker")
    if "scripts/project-stable-release.py" not in text:
        fail("release-attest.yml does not project the stable manifest")
    if "QUALIFICATION_FINAL_HEAD" not in text:
        fail("release-attest.yml does not bind qualification evidence to the tag")
    if "qualification_evidence_b64" not in text:
        fail("release-attest.yml does not accept retained qualification evidence")
    if "scripts/check-release-qualification-evidence.py" not in text:
        fail("release-attest.yml does not validate retained qualification evidence")
    if "QUALIFICATION_EVIDENCE_SHA256" not in text:
        fail("release-attest.yml does not bind qualification evidence SHA256")
    if "QUALIFICATION_CHATGPT_OWNER_UI_ACCEPTANCE" not in text:
        fail("release-attest.yml does not bind ChatGPT owner/UI acceptance")
    if "QUALIFICATION_CHATGPT_OWNER_EVIDENCE_SHA256" not in text:
        fail("release-attest.yml does not bind ChatGPT owner/UI evidence SHA256")
    if "qualification_chatgpt_owner_evidence_b64" not in text:
        fail("release-attest.yml does not accept the actual owner/UI evidence payload")
    if "scripts/check-chatgpt-owner-acceptance.py" not in text:
        fail("release-attest.yml does not revalidate owner/UI evidence")
    if "QUALIFICATION_MCP_ENDPOINT" not in text or "--expected-endpoint" not in text:
        fail("release-attest.yml does not bind owner/UI evidence to qualified public MCP endpoint")
    if "stable-release-qualification" not in text:
        fail("release-attest.yml lacks protected qualification environment")
    if "QUALIFICATION_TRUSTED_REVIEW" not in text:
        fail("release-attest.yml does not bind protected qualification review")
    if "needs.stable-qualification-approval.outputs.reviewed_sha256" not in text:
        fail("release-attest.yml does not bind protected qualification review SHA256")
    if "stable-release-owner-ui" not in text:
        fail("release-attest.yml lacks protected owner/UI environment")
    if "QUALIFICATION_TRUSTED_OWNER_UI_REVIEW" not in text:
        fail("release-attest.yml does not bind protected owner/UI review")
    if "needs.stable-owner-ui-approval.outputs.trusted_owner_ui_review" not in text:
        fail("release-attest.yml does not source owner/UI review from protected job")
    if "owner-ui-evidence-validation" not in text:
        fail("release-attest.yml does not prevalidate owner/UI evidence before protected approval")
    if "needs.stable-owner-ui-approval.outputs.reviewed_sha256" not in text:
        fail("release-attest.yml does not bind protected owner/UI review to evidence SHA256")
    if "QUALIFICATION_TRUSTED_OWNER_UI_REVIEW_SHA256" not in text:
        fail("release-attest.yml does not pass the protected owner/UI evidence digest to binding")
    for forbidden in (
        "inputs.qualification_chatgpt_owner_ui_acceptance",
        "inputs.qualification_chatgpt_owner_evidence_sha256",
        "inputs.qualification_chatgpt_owner_evidence_provenance_head",
        "inputs.qualification_trusted_owner_ui_review",
        "inputs.qualification_pass1_head",
        "inputs.qualification_pass2_head",
        "inputs.qualification_final_head",
        "inputs.qualification_trusted_review",
        "inputs.qualification_trusted_review_sha256",
    ):
        if forbidden in text:
            fail("release-attest.yml still trusts free-form owner gate input %s" % forbidden)
    if "source_head '$SOURCE_HEAD' != checked-out HEAD" in text:
        fail("release-attest.yml still rejects a content source_head")
    print("PASS WORKFLOW_CALLS_BINDING_CHECKER")


def test_development_provenance_commit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        init_repo(repo)
        content = git(repo, "rev-parse", "HEAD")
        provenance = stamp(repo, "development", content, content)
        proc = run_cli(
            repo,
            provenance,
            "refs/heads/main",
            provenance,
        )
        if proc.returncode != 0:
            fail(proc.stderr)
        outputs = dict(
            line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line
        )
        if outputs.get("release_commit") != provenance:
            fail("release_commit %s" % outputs)
        if outputs.get("content_commit") != content:
            fail("content_commit %s" % outputs)
        if outputs.get("channel") != "development":
            fail("channel %s" % outputs)
    print("PASS DEVELOPMENT_PROVENANCE_COMMIT")


def test_rejects_product_diff_and_mutable_ref() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        init_repo(repo)
        content = git(repo, "rev-parse", "HEAD")
        write(repo, "lib/product.sh", "echo changed\n")
        provenance = stamp(repo, "development", content, content)
        proc = run_cli(repo, provenance, "refs/heads/main", provenance)
        assert_fail(proc, "non-generated paths")
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        init_repo(repo)
        content = git(repo, "rev-parse", "HEAD")
        provenance = stamp(repo, "development", "main", content)
        proc = run_cli(repo, provenance, "refs/heads/main", provenance)
        assert_fail(proc, "40-char content SHA")
    print("PASS REJECT_UNQUALIFIED_TREE_AND_MUTABLE_REF")


def test_rejects_non_parent_and_wrong_dispatch() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        init_repo(repo)
        first = git(repo, "rev-parse", "HEAD")
        write(repo, "lib/product.sh", "echo second\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-m", "more product")
        parent = git(repo, "rev-parse", "HEAD")
        provenance = stamp(repo, "development", first, first)
        proc = run_cli(repo, provenance, "refs/heads/main", provenance)
        assert_fail(proc, "!= content parent %s" % parent)

        init_repo(repo)
        content = git(repo, "rev-parse", "HEAD")
        provenance = stamp(repo, "development", content, content)
        proc = run_cli(repo, content, "refs/heads/main", provenance)
        assert_fail(proc, "must be the provenance commit SHA")
        proc = run_cli(repo, provenance, "refs/heads/main", content)
        assert_fail(proc, "github.sha")
    print("PASS REJECT_NON_PARENT_AND_WRONG_DISPATCH")


def test_stable_and_rc_tags_point_at_provenance_commit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        init_repo(repo, channel="stable")
        content = git(repo, "rev-parse", "HEAD")
        write(
            repo,
            "VERSION",
            "PROJECT_VERSION=1.2.3\nFRP_VERSION=0.71.0\nRELEASE_CHANNEL=stable\n",
        )
        provenance = stamp(repo, "stable", "v1.2.3", content)
        git(repo, "tag", "v1.2.3", provenance)
        proc = run_cli(repo, "v1.2.3", "refs/tags/v1.2.3", provenance)
        assert_fail(proc, "FINAL_QUALIFIED_HEAD")
        proc = run_cli(repo, "v1.2.3", "refs/tags/v1.2.3", provenance, content)
        assert_fail(proc, "FINAL_QUALIFIED_HEAD")
        proc = run_cli(repo, "v1.2.3", "refs/tags/v1.2.3", provenance, provenance)
        if proc.returncode != 0:
            fail(proc.stderr)
        git(repo, "tag", "-d", "v1.2.3")
        git(repo, "tag", "v1.2.3", content)
        proc = run_cli(repo, "v1.2.3", "refs/tags/v1.2.3", provenance)
        assert_fail(proc, "not provenance HEAD")

        shutil.rmtree(repo)
        repo.mkdir()
        init_repo(repo, channel="preview")
        content = git(repo, "rev-parse", "HEAD")
        provenance = stamp(repo, "preview", "v1.2.3-rc.1", content)
        git(repo, "tag", "v1.2.3-rc.1", provenance)
        proc = run_cli(repo, "v1.2.3-rc.1", "refs/tags/v1.2.3-rc.1", provenance)
        if proc.returncode != 0:
            fail(proc.stderr)
        proc = run_cli(repo, "v1.2.3-rc.1", "refs/heads/main", provenance)
        assert_fail(proc, "dispatch this workflow from refs/tags/v1.2.3-rc.1")
    print("PASS STABLE_AND_RC_BIND_PROVENANCE_COMMIT")


def attestation_want_ref(channel: str, tag: str) -> str | None:
    """Same rule as release-attest.yml post-attestation verification."""
    return "refs/tags/%s" % tag if channel == "stable" else None


def test_validated_stable_tag_exposes_effective_channel() -> None:
    """Development manifest plus a qualified stable tag publishes as stable.

    Current behavior returns channel=development, so the verifier skips
    sourceRepositoryRef. This must fail until the effective channel is stable.
    """
    workflow = (ROOT / ".github/workflows/release-attest.yml").read_text(encoding="utf-8")
    if "want_ref = 'refs/tags/%s' % tag if channel == 'stable' else None" not in workflow:
        fail("post-attestation verifier does not key sourceRepositoryRef off channel")
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        init_repo(repo)
        write(
            repo,
            "VERSION",
            "PROJECT_VERSION=2.4.0\nFRP_VERSION=0.71.0\nRELEASE_CHANNEL=development\n",
        )
        git(repo, "add", "-A")
        git(repo, "commit", "-m", "set product version")
        content = git(repo, "rev-parse", "HEAD")
        before = git(repo, "rev-list", "--count", "HEAD")
        provenance = stamp(repo, "development", content, content, version="2.4.0")
        git(repo, "tag", "v2.4.0", provenance)
        committed = (repo / "release-manifest.json").read_text(encoding="utf-8")
        if '"channel": "development"' not in committed:
            fail("fixture manifest is not development")
        proc = run_cli(repo, "v2.4.0", "refs/tags/v2.4.0", provenance, provenance)
        if proc.returncode != 0:
            fail(proc.stderr)
        outputs = dict(
            line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line
        )
        if outputs.get("channel") != "stable":
            fail(
                "effective channel %s; verifier would skip sourceRepositoryRef refs/tags/v2.4.0"
                % outputs.get("channel")
            )
        if outputs.get("expected_tag") != "v2.4.0":
            fail("expected_tag %s" % outputs)
        want_ref = attestation_want_ref(outputs["channel"], outputs["expected_tag"])
        if want_ref != "refs/tags/v2.4.0":
            fail("sourceRepositoryRef want %s" % want_ref)
        if (repo / "release-manifest.json").read_text(encoding="utf-8") != committed:
            fail("binding rewrote the committed manifest")
        if json.loads(committed)["channel"] != "development":
            fail("committed manifest channel is no longer development")
        if git(repo, "rev-list", "--count", "HEAD") != str(int(before) + 1):
            fail("binding created a post-qualification commit")
        if git(repo, "status", "--porcelain"):
            fail("binding dirtied the worktree")
    print("PASS EFFECTIVE_STABLE_TAG_CHANNEL")


def test_stable_requires_protected_qualification_review() -> None:
    head = "a" * 40
    parent = "b" * 40
    base = dict(
        project_version="1.2.3",
        manifest_version="1.2.3",
        channel="stable",
        git_ref="v1.2.3",
        source_head=parent,
        immutable_source_ref="v1.2.3",
        head=head,
        parent=parent,
        input_ref="v1.2.3",
        workflow_ref="refs/tags/v1.2.3",
        workflow_sha=head,
        changed_paths=("release-manifest.json",),
        tag_commits={"v1.2.3": head},
        clean=True,
        pass1_head=head,
        pass2_head=head,
        final_qualified_head=head,
        qualification_evidence_sha256="e" * 64,
    )
    try:
        checker.evaluate(checker.BindingFacts(**base))
    except checker.BindingError as exc:
        if not any("protected qualification review must be PASS" in err for err in exc.errors):
            fail("missing protected qualification review error: %s" % exc.errors)
    else:
        fail("stable tag accepted without protected qualification review")

    bad_sha = dict(
        base,
        trusted_qualification_review="PASS",
        trusted_qualification_evidence_sha256="f" * 64,
    )
    try:
        checker.evaluate(checker.BindingFacts(**bad_sha))
    except checker.BindingError as exc:
        if not any("must match qualification evidence SHA256" in err for err in exc.errors):
            fail("review/evidence digest mismatch error not reported: %s" % exc.errors)
    else:
        fail("stable tag accepted with mismatched reviewed qualification SHA256")

    approved = dict(
        base,
        trusted_qualification_review="PASS",
        trusted_qualification_evidence_sha256="e" * 64,
    )
    result = checker.evaluate(checker.BindingFacts(**approved))
    if result.get("channel") != "stable":
        fail("protected qualification review did not permit stable binding: %s" % result)
    print("PASS STABLE_REQUIRES_PROTECTED_QUALIFICATION_REVIEW")


def test_v240_stable_requires_chatgpt_owner_evidence() -> None:
    head = "a" * 40
    parent = "b" * 40
    base = dict(
        project_version="2.4.0",
        manifest_version="2.4.0",
        channel="development",
        git_ref=parent,
        source_head=parent,
        immutable_source_ref=parent,
        head=head,
        parent=parent,
        input_ref="v2.4.0",
        workflow_ref="refs/tags/v2.4.0",
        workflow_sha=head,
        changed_paths=("release-manifest.json",),
        tag_commits={"v2.4.0": head},
        clean=True,
        pass1_head=head,
        pass2_head=head,
        final_qualified_head=head,
        qualification_evidence_sha256="e" * 64,
        trusted_qualification_review="PASS",
        trusted_qualification_evidence_sha256="e" * 64,
    )
    try:
        checker.evaluate(checker.BindingFacts(**base))
    except checker.BindingError as exc:
        if not any("owner/UI acceptance" in err for err in exc.errors):
            fail("missing owner/UI evidence error not reported: %s" % exc.errors)
    else:
        fail("v2.4.0 stable tag accepted without ChatGPT owner/UI evidence")
    base.update(
        chatgpt_owner_ui_acceptance="PASS",
        chatgpt_owner_evidence_sha256="c" * 64,
        chatgpt_owner_evidence_provenance_head=head,
        trusted_owner_ui_review="PASS",
        trusted_owner_ui_evidence_sha256="c" * 64,
    )
    result = checker.evaluate(checker.BindingFacts(**base))
    if result.get("channel") != "stable":
        fail("owner evidence did not permit validated stable publication: %s" % result)
    print("PASS V240_STABLE_REQUIRES_CHATGPT_OWNER_EVIDENCE")


def test_v240_stable_rejects_mismatched_protected_owner_evidence_digest() -> None:
    head = "a" * 40
    parent = "b" * 40
    facts = checker.BindingFacts(
        project_version="2.4.0",
        manifest_version="2.4.0",
        channel="development",
        git_ref=parent,
        source_head=parent,
        immutable_source_ref=parent,
        head=head,
        parent=parent,
        input_ref="v2.4.0",
        workflow_ref="refs/tags/v2.4.0",
        workflow_sha=head,
        changed_paths=("release-manifest.json",),
        tag_commits={"v2.4.0": head},
        clean=True,
        pass1_head=head,
        pass2_head=head,
        final_qualified_head=head,
        qualification_evidence_sha256="e" * 64,
        trusted_qualification_review="PASS",
        trusted_qualification_evidence_sha256="e" * 64,
        chatgpt_owner_ui_acceptance="PASS",
        chatgpt_owner_evidence_sha256="c" * 64,
        chatgpt_owner_evidence_provenance_head=head,
        trusted_owner_ui_review="PASS",
        trusted_owner_ui_evidence_sha256="d" * 64,
    )
    try:
        checker.evaluate(facts)
    except checker.BindingError as exc:
        if not any("owner/UI review SHA256 must match" in err for err in exc.errors):
            fail("mismatched protected owner evidence digest not reported: %s" % exc.errors)
    else:
        fail("mismatched protected owner evidence digest was accepted")
    print("PASS V240_STABLE_BINDS_PROTECTED_OWNER_REVIEW_TO_EVIDENCE_DIGEST")


def test_v240_stable_requires_protected_owner_review() -> None:
    head = "a" * 40
    parent = "b" * 40
    facts = checker.BindingFacts(
        project_version="2.4.0",
        manifest_version="2.4.0",
        channel="development",
        git_ref=parent,
        source_head=parent,
        immutable_source_ref=parent,
        head=head,
        parent=parent,
        input_ref="v2.4.0",
        workflow_ref="refs/tags/v2.4.0",
        workflow_sha=head,
        changed_paths=("release-manifest.json",),
        tag_commits={"v2.4.0": head},
        clean=True,
        pass1_head=head,
        pass2_head=head,
        final_qualified_head=head,
        qualification_evidence_sha256="e" * 64,
        trusted_qualification_review="PASS",
        trusted_qualification_evidence_sha256="e" * 64,
        chatgpt_owner_ui_acceptance="PASS",
        chatgpt_owner_evidence_sha256="c" * 64,
        chatgpt_owner_evidence_provenance_head=head,
    )
    try:
        checker.evaluate(facts)
    except checker.BindingError as exc:
        if not any("protected owner/UI review" in err for err in exc.errors):
            fail("protected owner/UI review error not reported: %s" % exc.errors)
    else:
        fail("protected owner/UI review was not required")
    print("PASS V240_STABLE_REQUIRES_PROTECTED_OWNER_REVIEW")


def test_release_qualification_evidence_binding() -> None:
    head = git(ROOT, "rev-parse", "HEAD")

    def summary(pass_name: str) -> dict:
        return {
            "schema_version": 1,
            "pass_name": pass_name,
            "git_head": head,
            "public_mcp_endpoint": "https://drlink.example.com/mcp",
            "gates": {
                "FROZEN_HEAD": head,
                f"{pass_name}_HEAD": head,
                "END_HEAD": head,
                "HEAD_UNCHANGED": "YES",
                "FUNCTIONAL_FULL_MATRIX": "PASS",
                "RUN_ALL": "PASS",
                pass_name: "PASS",
            },
            "evidence_paths": {
                "summary.txt": True,
                "matrix.log": True,
                "perf/baseline.json": True,
            },
            "final_status": "PASS",
        }

    def digest(value: dict) -> str:
        raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    pass1 = summary("PASS1")
    pass2 = summary("PASS2")
    evidence = {
        "schema_version": 1,
        "status": "PASS",
        "pass1_head": head,
        "pass2_head": head,
        "final_qualified_head": head,
        "public_mcp_endpoint": "https://drlink.example.com/mcp",
        "pass1_summary_sha256": digest(pass1),
        "pass2_summary_sha256": digest(pass2),
        "pass1_summary": pass1,
        "pass2_summary": pass2,
    }

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "qualification-evidence.json"

        def check(doc: dict) -> subprocess.CompletedProcess[str]:
            path.write_text(
                json.dumps(doc, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return subprocess.run(
                [
                    sys.executable,
                    str(QUALIFICATION_SCRIPT),
                    "--root",
                    str(ROOT),
                    "--evidence",
                    str(path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        ok = check(evidence)
        if ok.returncode != 0 or "QUALIFICATION_EVIDENCE=PASS" not in ok.stdout:
            fail("valid qualification evidence rejected: %s" % ok.stderr)

        mismatched_endpoint = json.loads(json.dumps(evidence))
        mismatched_endpoint["pass2_summary"]["public_mcp_endpoint"] = "https://other.example.com/mcp"
        mismatched_endpoint["pass2_summary_sha256"] = digest(mismatched_endpoint["pass2_summary"])
        rejected = check(mismatched_endpoint)
        if rejected.returncode == 0 or "public_mcp_endpoint mismatch" not in rejected.stderr:
            fail("mismatched qualification MCP endpoint was accepted: %s" % rejected.stderr)

        no_summaries = dict(evidence)
        no_summaries.pop("pass1_summary")
        no_summaries.pop("pass2_summary")
        rejected = check(no_summaries)
        if rejected.returncode == 0:
            fail("caller HEAD strings without retained summaries were accepted")

        failed_gate = json.loads(json.dumps(evidence))
        failed_gate["pass2_summary"]["gates"]["RUN_ALL"] = "FAIL"
        failed_gate["pass2_summary_sha256"] = digest(failed_gate["pass2_summary"])
        rejected = check(failed_gate)
        if rejected.returncode == 0 or "terminal blocking gate RUN_ALL=FAIL" not in rejected.stderr:
            fail("FAIL gate evidence was accepted: %s" % rejected.stderr)

        tampered = json.loads(json.dumps(evidence))
        tampered["pass1_summary"]["evidence_paths"]["matrix.log"] = False
        rejected = check(tampered)
        if rejected.returncode == 0 or "does not match embedded pass1_summary" not in rejected.stderr:
            fail("tampered summary digest was accepted: %s" % rejected.stderr)

    print("PASS RELEASE_QUALIFICATION_EVIDENCE_BINDING")


def test_self_reference_is_rejected() -> None:
    head = "a" * 40
    parent = "b" * 40
    facts = checker.BindingFacts(
        project_version="1.2.3",
        manifest_version="1.2.3",
        channel="development",
        git_ref=head,
        source_head=head,
        immutable_source_ref=head,
        head=head,
        parent=parent,
        input_ref=head,
        workflow_ref="refs/heads/main",
        workflow_sha=head,
        changed_paths=("release-manifest.json",),
        tag_commits={},
        clean=True,
    )
    try:
        checker.evaluate(facts)
    except checker.BindingError as exc:
        if not any("self-referential" in err for err in exc.errors):
            fail("errors=%s" % exc.errors)
    else:
        fail("self-referential source_head was accepted")
    print("PASS REJECT_SELF_REFERENTIAL_SHA")


def main() -> int:
    test_workflow_uses_checker()
    test_development_provenance_commit()
    test_rejects_product_diff_and_mutable_ref()
    test_rejects_non_parent_and_wrong_dispatch()
    test_stable_and_rc_tags_point_at_provenance_commit()
    test_validated_stable_tag_exposes_effective_channel()
    test_stable_requires_protected_qualification_review()
    test_v240_stable_requires_chatgpt_owner_evidence()
    test_v240_stable_rejects_mismatched_protected_owner_evidence_digest()
    test_v240_stable_requires_protected_owner_review()
    test_release_qualification_evidence_binding()
    test_self_reference_is_rejected()
    print("RELEASE_ATTEST_BINDING_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

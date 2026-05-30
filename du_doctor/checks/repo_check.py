"""Data Universe repository checks (git state + expected files).

Uses plain ``git`` via subprocess (no GitPython dependency). All git calls are
read-only except a best-effort ``git fetch`` which only updates remote-tracking
refs and never touches your working tree or commits.
"""

from __future__ import annotations

from pathlib import Path

from du_doctor.checks.base import BaseCheck
from du_doctor.models import CheckCategory, CheckResult, CheckStatus
from du_doctor.utils.files import expand_path
from du_doctor.utils.shell import command_exists, run_command


class RepoCheck(BaseCheck):
    category = CheckCategory.REPO
    name = "repo"

    def run(self) -> list[CheckResult]:
        repo_path = expand_path(self.config.subnet_repo_path)
        if repo_path is None:
            return [
                self.result(
                    "repo_path",
                    "Repo path",
                    CheckStatus.SKIPPED,
                    "No subnet_repo_path configured.",
                    suggested_fixes=[
                        "Set subnet_repo_path in config or pass --repo-path /path/to/data-universe.",
                    ],
                )
            ]

        results: list[CheckResult] = []

        # 1. Path exists.
        if not repo_path.exists():
            results.append(
                self.result(
                    "repo_path",
                    "Repo path",
                    CheckStatus.CRITICAL,
                    f"Repo path does not exist: {repo_path}",
                    details={"path": str(repo_path)},
                    suggested_fixes=[
                        f"git clone {self.config.subnet_repo_url} {repo_path}",
                        "Or point --repo-path at your existing clone.",
                    ],
                )
            )
            return results
        results.append(
            self.result(
                "repo_path",
                "Repo path",
                CheckStatus.OK,
                f"Found repo directory: {repo_path}",
                details={"path": str(repo_path)},
            )
        )

        # Expected files don't need git; check them regardless.
        results.append(self._check_expected_files(repo_path))

        if not command_exists("git"):
            results.append(
                self.result(
                    "git_available",
                    "git availability",
                    CheckStatus.WARNING,
                    "git is not installed; cannot check branch/remote/behind status.",
                    suggested_fixes=["Install git (e.g. `sudo apt install git`)."],
                )
            )
            return results

        # 2. Is a git repo.
        is_repo = run_command(["git", "-C", str(repo_path), "rev-parse", "--is-inside-work-tree"])
        if not (is_repo.ok and is_repo.stdout.strip() == "true"):
            results.append(
                self.result(
                    "repo_is_git",
                    "Git repository",
                    CheckStatus.CRITICAL,
                    f"{repo_path} is not a git repository.",
                    details={"path": str(repo_path)},
                    suggested_fixes=[
                        f"Clone the repo properly: git clone {self.config.subnet_repo_url}",
                    ],
                )
            )
            return results
        results.append(
            self.result("repo_is_git", "Git repository", CheckStatus.OK, "Valid git repository.")
        )

        # 3. Remote origin.
        results.append(self._check_remote(repo_path))
        # 4. Branch.
        branch = self._current_branch(repo_path)
        results.append(self._check_branch(branch))
        # 5. Behind upstream.
        results.append(self._check_behind(repo_path))
        # 6. Dirty tree.
        results.append(self._check_dirty(repo_path))

        return results

    # ------------------------------------------------------------------ #
    def _check_remote(self, repo_path: Path) -> CheckResult:
        res = run_command(["git", "-C", str(repo_path), "remote", "get-url", "origin"])
        url = res.stdout.strip()
        if not res.ok or not url:
            return self.result(
                "repo_remote",
                "Git remote",
                CheckStatus.WARNING,
                "No 'origin' remote configured.",
                suggested_fixes=[f"git remote add origin {self.config.subnet_repo_url}"],
            )
        if "macrocosm-os/data-universe" in url:
            return self.result(
                "repo_remote",
                "Git remote",
                CheckStatus.OK,
                "origin points at macrocosm-os/data-universe.",
                details={"url": url},
            )
        return self.result(
            "repo_remote",
            "Git remote",
            CheckStatus.WARNING,
            f"origin does not point at macrocosm-os/data-universe (found: {url}).",
            details={"url": url},
            suggested_fixes=[
                "This may be a fork — that can be intentional.",
                f"Official upstream: {self.config.subnet_repo_url}",
            ],
        )

    def _current_branch(self, repo_path: Path) -> str:
        res = run_command(["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"])
        return res.stdout.strip()

    def _check_branch(self, branch: str) -> CheckResult:
        if branch == "HEAD" or not branch:
            return self.result(
                "repo_branch",
                "Git branch",
                CheckStatus.WARNING,
                "Repository is in a detached HEAD state.",
                details={"branch": branch or "unknown"},
                suggested_fixes=[
                    "Check out a branch (e.g. `git checkout main`) so updates are easy."
                ],
            )
        return self.result(
            "repo_branch",
            "Git branch",
            CheckStatus.OK,
            f"On branch '{branch}'.",
            details={"branch": branch},
        )

    def _check_behind(self, repo_path: Path) -> CheckResult:
        # Best-effort fetch (updates remote-tracking refs only). May fail offline.
        # Disable any credential/terminal prompt so a private or unreachable
        # remote fails fast instead of hanging until the timeout.
        no_prompt_env = {"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "GCM_INTERACTIVE": "never"}
        fetch = run_command(
            ["git", "-C", str(repo_path), "fetch", "origin", "--quiet"],
            timeout=45,
            env=no_prompt_env,
        )
        upstream = self._default_upstream(repo_path)
        if upstream is None:
            return self.result(
                "repo_behind",
                "Repo up-to-date",
                CheckStatus.SKIPPED,
                "Could not determine the upstream branch (origin/main or origin/master).",
                details={"fetch_ok": fetch.ok},
            )

        count_res = run_command(
            ["git", "-C", str(repo_path), "rev-list", "--count", f"HEAD..{upstream}"]
        )
        if not count_res.ok or not count_res.stdout.strip().isdigit():
            return self.result(
                "repo_behind",
                "Repo up-to-date",
                CheckStatus.SKIPPED,
                f"Could not compare local HEAD to {upstream}"
                + (" (fetch failed — offline?)." if not fetch.ok else "."),
                details={"upstream": upstream, "fetch_ok": fetch.ok},
            )
        behind = int(count_res.stdout.strip())
        details = {"behind": behind, "upstream": upstream, "fetch_ok": fetch.ok}
        warn = self.config.thresholds.repo_behind_warning_commits
        crit = self.config.thresholds.repo_behind_critical_commits

        if behind == 0:
            return self.result(
                "repo_behind",
                "Repo up-to-date",
                CheckStatus.OK,
                f"Up to date with {upstream}.",
                details=details,
            )
        fixes = [f"cd {repo_path} && git pull", "Then restart the miner with PM2 after updating."]
        if behind >= crit:
            return self.result(
                "repo_behind",
                "Repo up-to-date",
                CheckStatus.CRITICAL,
                f"{behind} commits behind {upstream}. An outdated miner can score poorly.",
                details=details,
                suggested_fixes=fixes,
            )
        if behind >= warn:
            return self.result(
                "repo_behind",
                "Repo up-to-date",
                CheckStatus.WARNING,
                f"{behind} commits behind {upstream}.",
                details=details,
                suggested_fixes=fixes,
            )
        return self.result(
            "repo_behind",
            "Repo up-to-date",
            CheckStatus.OK,
            f"{behind} commit(s) behind {upstream} (within threshold).",
            details=details,
        )

    def _default_upstream(self, repo_path: Path) -> str | None:
        sym = run_command(["git", "-C", str(repo_path), "symbolic-ref", "refs/remotes/origin/HEAD"])
        if sym.ok and sym.stdout.strip():
            ref = sym.stdout.strip()  # e.g. refs/remotes/origin/main
            return ref.replace("refs/remotes/", "")
        for candidate in ("origin/main", "origin/master"):
            verify = run_command(
                ["git", "-C", str(repo_path), "rev-parse", "--verify", "--quiet", candidate]
            )
            if verify.ok:
                return candidate
        return None

    def _check_dirty(self, repo_path: Path) -> CheckResult:
        res = run_command(["git", "-C", str(repo_path), "status", "--porcelain"])
        changes = [line for line in res.stdout.splitlines() if line.strip()]
        if changes:
            return self.result(
                "repo_dirty",
                "Working tree",
                CheckStatus.WARNING,
                f"{len(changes)} uncommitted change(s) in the working tree "
                "(local changes may be intentional).",
                details={"changed_files": len(changes)},
                evidence=changes[:15],
                suggested_fixes=[
                    "If these edits are intentional, you can ignore this.",
                    "Otherwise `git status` and reconcile before pulling updates.",
                ],
            )
        return self.result(
            "repo_dirty",
            "Working tree",
            CheckStatus.OK,
            "Working tree is clean.",
        )

    def _check_expected_files(self, repo_path: Path) -> CheckResult:
        du = self.config.data_universe
        missing_required: list[str] = []
        present: list[str] = []
        for rel in du.expected_files:
            if (repo_path / rel).exists():
                present.append(rel)
            else:
                missing_required.append(rel)

        missing_optional = [
            rel for rel in du.expected_optional_files if not (repo_path / rel).exists()
        ]
        details = {
            "present": present,
            "missing_required": missing_required,
            "missing_optional": missing_optional,
        }

        miner_missing = any("miner.py" in m for m in missing_required)
        if miner_missing:
            return self.result(
                "repo_files",
                "Expected files",
                CheckStatus.CRITICAL,
                "neurons/miner.py is missing — this does not look like a Data Universe repo.",
                details=details,
                suggested_fixes=[
                    "Re-clone the repository or point --repo-path at the correct directory.",
                ],
            )
        if missing_required:
            return self.result(
                "repo_files",
                "Expected files",
                CheckStatus.WARNING,
                f"Missing expected files: {', '.join(missing_required)}.",
                details=details,
            )
        msg = "All required Data Universe files present."
        if missing_optional:
            msg += f" Optional files not found: {', '.join(missing_optional)}."
        return self.result("repo_files", "Expected files", CheckStatus.OK, msg, details=details)

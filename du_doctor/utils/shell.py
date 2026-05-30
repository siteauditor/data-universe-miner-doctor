"""A tiny, *safe* subprocess wrapper.

Rules enforced here:
  * Never use ``shell=True`` (no shell injection surface).
  * Never raise — every failure mode returns a ``CommandResult``.
  * Always time out so a hung child can't hang the doctor.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence, Union


@dataclass
class CommandResult:
    """The result of attempting to run an external command."""

    found: bool  # was the executable found on PATH?
    ok: bool  # did it exit 0?
    returncode: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        """Combined stdout+stderr, convenient for scanning version strings."""
        return f"{self.stdout}\n{self.stderr}".strip()


def command_exists(name: str) -> bool:
    """True if ``name`` resolves on PATH."""
    return shutil.which(name) is not None


def run_command(
    args: Union[str, Sequence[str]],
    timeout: float = 15.0,
    cwd: Optional[Union[str, Path]] = None,
    env: Optional[Mapping[str, str]] = None,
) -> CommandResult:
    """Run a command and capture output. Always returns a ``CommandResult``.

    ``args`` should be a list (e.g. ``["git", "status"]``). A bare string is
    treated as a single executable with no arguments. ``env`` is merged on top
    of the current environment (use it to e.g. disable interactive prompts).
    """
    if isinstance(args, str):
        args = [args]
    args = [str(a) for a in args]

    if not args or not command_exists(args[0]):
        return CommandResult(
            found=False, ok=False, returncode=127, stdout="", stderr="command not found"
        )

    run_env = None
    if env:
        run_env = {**os.environ, **env}

    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
            shell=False,
            errors="replace",
            env=run_env,
        )
        return CommandResult(
            found=True,
            ok=proc.returncode == 0,
            returncode=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )
    except subprocess.TimeoutExpired:
        return CommandResult(
            found=True, ok=False, returncode=124, stdout="", stderr=f"timed out after {timeout}s"
        )
    except Exception as exc:  # noqa: BLE001 - defensive: never let a check crash
        return CommandResult(found=True, ok=False, returncode=1, stdout="", stderr=str(exc))

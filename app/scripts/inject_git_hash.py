# serialdbg-001 (TASK-056a): inject GIT_REV define from `git rev-parse`.
# Falls back to "unknown" when git is unavailable or the tree is not a repo.
# Dirty-tree marker: trailing "+" when `git diff --quiet` returns non-zero.
import subprocess
Import("env")
try:
    rev = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"],
        stderr=subprocess.DEVNULL
    ).decode().strip()
    dirty = subprocess.call(["git", "diff", "--quiet"],
                            stderr=subprocess.DEVNULL)
    tag = rev + ("+" if dirty else "")
except Exception:
    tag = "unknown"
env.Append(CPPFLAGS=[f'-DGIT_REV=\'"{tag}"\''])

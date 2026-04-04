# Coding Task

Task ID: TASK-20260404-LWAQ
Attempt ID: ATTEMPT-20260404-OJ8S

## Summary
修复 setup.ps1 Python 检测崩溃问题：当系统完全没有安装 python 命令时，PowerShell 第10行 (python --version 2>&1) 抛出 CommandNotFoundException（终止性错误），导致 为 null，第11行 .Trim() 报 InvalidOp...

## Planned Steps
1. Implement the requested change according to the provided references.

## Files
No explicit file list was extracted from the request.

## Acceptance Criteria
1. [REQUIRED] Implementation satisfies the original request without unrelated changes.

## References
- No explicit references were provided.

## Constraints
- Keep changes focused on the request.
- Do not introduce unrelated refactors.
- Preserve existing conventions when possible.
- If context is missing, report the gap explicitly instead of guessing.

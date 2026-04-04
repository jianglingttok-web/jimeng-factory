# Coding Task

Task ID: TASK-20260404-1RG0
Attempt ID: ATTEMPT-20260404-WAAU

## Summary
修复 setup.ps1：运营机器 Python 3.14 安装时未包含 pip，导致 [2/4] 报 'No module named pip'。修复方法：在 setup.ps1 的 [2/4] 安装依赖部分（即 'python -m pip install -r' 那行之前），插入 pip bootstrap...

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

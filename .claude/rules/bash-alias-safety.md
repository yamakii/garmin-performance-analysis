# Bash Alias Safety

## CRITICAL: This environment has interactive aliases (cp -i, mv -i, rm -i)

Bashツールでファイル操作する際、対話的プロンプトでハングするのを防ぐ：

- `cp` → `command cp`
- `mv` → `command mv`
- `rm` → `command rm`

# Backward Compatibility Rules

## Principle: Do not create backward-compatible aliases or shims

When refactoring (renaming, moving, extracting), update all call sites in the same change.

## Rules

1. **No module-level aliases**: Do not add `_old_name = new_module.new_name` for re-export
2. **No re-exports**: Do not add symbols to `__all__` for import convenience from old paths
3. **No parameter shims**: Do not accept deprecated parameter names and map them internally
4. **Update tests simultaneously**: When moving a function, update test imports in the same commit
5. **Verify no callers before removing**: Use `find_referencing_symbols` or `grep` to confirm zero usage

## If temporary compatibility is truly needed

- Add a comment with removal date: `# TODO(YYYY-MM-DD): Remove backward-compatible alias`
- Complete removal within the same PR if possible
- Never leave aliases without a removal date

## Common patterns to avoid

```python
# BAD: module-level alias
_old_function = NewModule.new_function

# BAD: re-export in __all__
__all__ = ["NewClass", "OldClass"]  # OldClass for backward compat

# BAD: parameter shim
def render(*, new_param=None, old_param=None):
    if old_param and not new_param:
        new_param = old_param

# GOOD: just update all call sites
from new_module import new_function  # in all files that use it
```

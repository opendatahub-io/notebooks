# /command-name - Brief Description

## Purpose
[Clear statement of what this command does and why]

## Prerequisites
- [List all requirements]
- [Dependencies, permissions needed]
- [Tools or configuration required]

## Usage

```
/command-name [arguments]
```

## MANDATORY EXECUTION REQUIREMENTS

**⚠️ CRITICAL: This command specification MUST be followed exactly. NO shortcuts allowed.**

When executing this command, you MUST:

1. **Execute ALL steps sequentially** - Steps are numbered 1-N. Execute every single one.
2. **Perform ALL actions listed** - Each step has an "Actions:" section. Execute every action listed.
3. **Display ALL required output** - Each step has "Expected Output" sections. Display the exact format shown.
4. **Make ALL checks specified** - If a step says "check for X, Y, and Z", check all three, not just one.
5. **Use ALL specified tools** - If a step says "Use tool X to do Y", use that exact tool.
6. **Handle ALL error cases** - Follow the error handling instructions in each step.
7. **Generate ALL artifacts** - Create all files, directories, and reports specified.

**Verification Checklist - MUST complete before marking command as done:**
- [ ] All N steps executed
- [ ] All tools called as specified
- [ ] All files/directories created as specified
- [ ] All output displayed in the exact format shown
- [ ] All reports/artifacts generated

**If you find yourself thinking "I'll skip this" or "this is similar enough":**
- STOP immediately
- Go back and execute the step exactly as written
- Remember: The user created this specification for a reason

## Execution Policy

**Permission Model:**
- **Read-only commands:** Execute without asking permission (`ls`, `cat`, `less`, `head`, `tail`, file reads, directory browsing)
- **Exception:** Ask permission only when reading potentially sensitive files (credentials, tokens, private keys, `.env` files, secrets)
- **Write operations:** Always ask permission for file modifications, deletions, or destructive commands

## Process

**Total Steps: N**

Before starting, acknowledge that you will execute all N steps completely. As you complete each step, mark it in your response with: ✅ Step X/N Complete

### 1. [Step Name]

**Objective:** [What this step achieves]

**Actions:**
- [Specific action to perform]
- [Another specific action]
- [Tool to use: `tool_name` with parameters X, Y]

**Expected Output:**
```
[Exact output format to display]
✓ Item 1: Value
✓ Item 2: Value
```

**Error Handling:**
- If [condition], then [action]
- Common error: [error message] → Solution: [fix]

### 2. [Next Step]

[Continue pattern...]

## Output

The command produces:

1. **Console Output:** [What user sees in real-time]
2. **Files Created:** [List of files]
3. **Artifacts:** [List of artifacts]

## Success Criteria

Command is successful when:
- ✓ [Criterion 1]
- ✓ [Criterion 2]
- ✓ [All steps completed]

## Error Handling

### Error: [Error Name]

**Symptom:**
```
[Error message or indication]
```

**Common Causes:**
- [Cause 1]
- [Cause 2]

**Solution:**
1. [Step 1 to fix]
2. [Step 2 to fix]
3. [Verification step]

## Examples

### Successful Execution

```
Running /command-name...

[1/N] [Step name]...
✓ [Output line 1]
✓ [Output line 2]

[2/N] [Next step]...
✓ [Output]

...

✅ Command Complete!

Next Steps:
1. [Recommended action 1]
2. [Recommended action 2]
```

### Execution with Warnings

```
Running /command-name...

[1/N] [Step name]...
⚠ [Warning message]
ℹ️  [Information]

...
```

## Integration with Other Commands

**Before this command:**
- [Prerequisites]

**After this command:**
- [Next steps]
- [Related commands]

## Tips

1. **[Tip category]:**
   - [Specific tip]
   - [Usage pattern]

2. **[Another category]:**
   - [Guidance]

## See Also

- `/related-command` - [Brief description]
- `file.md` - [Documentation reference]

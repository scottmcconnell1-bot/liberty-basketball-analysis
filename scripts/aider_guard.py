#!/usr/bin/env python3
"""
Aider invocation guard for liberty-basketball-analysis.

Prevents common invocation errors:
- --msg-file (not a valid Aider flag)
- Malformed pytest -k expressions passed as positional args
- Missing --message-file when using --message

Usage:
    python scripts/aider_guard.py [AIDER_ARGS...]
    # or
    aider_guard [AIDER_ARGS...]  (if added to PATH)
"""

import subprocess
import sys
import re


VALID_AIDER_FLAGS = {
    # Core flags
    '--message', '-m',
    '--message-file',  # CORRECT flag (not --msg-file)
    '--file', '-f',
    '--read', '-r',
    '--yes', '-y',
    '--no-auto-commits',
    '--commit',
    '--no-commit',
    '--dry-run',
    '--verbose', '-v',
    '--model',
    '--weak-model',
    '--editor-model',
    '--show-model-warnings',
    '--no-show-model-warnings',
    '--stream',
    '--no-stream',
    '--pretty',
    '--no-pretty',
    '--chat-language',
    '--encoding',
    '--config',
    '--no-config',
    '--load', '-l',
    '--save', '-s',
    '--exit', '-x',
    '--no-input-history',
    '--no-git',
    '--git',
    '--git-ignore',
    '--show-diffs',
    '--no-show-diffs',
    '--attribute-author',
    '--no-attribute-author',
    '--attribute-committer',
    '--no-attribute-committer',
    '--attribute-commit-message-author',
    '--no-attribute-commit-message-author',
    '--commit-message-author',
    '--commit-message-committer',
}

# Known invalid flags that users commonly mistake
INVALID_FLAGS = {
    '--msg-file': '--message-file',
    '--msg': '--message',
    '--commit-msg': '--message',
    '--pytest': None,  # pytest args go AFTER --, not as Aider flags
}


def validate_args(args):
    """Validate Aider arguments, return (is_valid, error_msg, corrected_args)"""
    corrected = []
    i = 0
    while i < len(args):
        arg = args[i]
        
        # Check for known invalid flags
        if arg in INVALID_FLAGS:
            suggestion = INVALID_FLAGS[arg]
            if suggestion:
                return False, f"Invalid flag: {arg}. Did you mean {suggestion}?", None
            else:
                return False, f"Invalid flag: {arg}. pytest -k expressions go after -- separator.", None
        
        # Check for pytest -k expressions mistakenly passed as positional args
        if arg.startswith('-k') or arg.startswith('--keyword'):
            return False, f"pytest argument {arg} must come after '--' separator (e.g., aider ... -- -k 'not test_foo')", None
        
        # Validate known flags have their required values
        if arg in ('--message', '-m', '--message-file', '--file', '-f', '--read', '-r', '--model', '--weak-model', '--editor-model', '--chat-language', '--encoding', '--config', '--load', '-l', '--save', '-s'):
            if i + 1 >= len(args):
                return False, f"Flag {arg} requires a value", None
            # Skip the value
            corrected.extend([arg, args[i + 1]])
            i += 2
            continue
        
        # Boolean flags
        if arg.startswith('--') or arg.startswith('-'):
            if arg not in VALID_AIDER_FLAGS and not arg.startswith('--'):  # allow unknown --flags
                # Warn but don't block
                pass
        
        corrected.append(arg)
        i += 1
    
    return True, None, corrected


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/aider_guard.py [AIDER_ARGS...]")
        print("Example: python scripts/aider_guard.py --message-file MSG.md -- -k 'not test_foo'")
        sys.exit(1)
    
    # Split at -- separator
    try:
        separator_idx = sys.argv.index('--')
        aider_args = sys.argv[1:separator_idx]
        pytest_args = sys.argv[separator_idx + 1:]
    except ValueError:
        aider_args = sys.argv[1:]
        pytest_args = []
    
    # Validate Aider args
    valid, error, corrected = validate_args(aider_args)
    if not valid:
        print(f"[AIDER GUARD] ❌ {error}", file=sys.stderr)
        sys.exit(2)
    
    # Build command
    cmd = ['aider'] + corrected
    if pytest_args:
        cmd += ['--'] + pytest_args
    
    print(f"[AIDER GUARD] Running: {' '.join(cmd)}", file=sys.stderr)
    
    # Execute
    result = subprocess.run(cmd, cwd='/mnt/c/Users/scott/Documents/liberty-basketball-analysis')
    sys.exit(result.returncode)


if __name__ == '__main__':
    main()
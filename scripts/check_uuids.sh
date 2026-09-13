#!/usr/bin/env bash
#
# Pre-commit hook: scan staged files for UUIDs and prompt the user
# to confirm each one belongs in the codebase. Fails if any are rejected.

set -euo pipefail

UUID_RE='[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'

# --scan mode: report all UUIDs without interactive prompts
# Usage: scripts/check_uuids.sh [--scan] [files...]
#   No args:        scans all git-tracked files interactively
#   --scan:         scans all git-tracked files, report-only (no prompts)
#   files...:       scans given files interactively (used by pre-commit)
#   --scan files:   scans given files, report-only
SCAN_MODE=false
if [[ "${1:-}" == "--scan" ]]; then
    SCAN_MODE=true
    shift
fi

# Default to all git-tracked files when no files are given
if [[ $# -eq 0 ]]; then
    set -- $(git ls-files --cached)
fi

# Whitelist of accepted UUIDs (one per line)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ALLOWED_FILE="$SCRIPT_DIR/allowed_uuids.txt"
touch "$ALLOWED_FILE"

rejected=0
seen=()

for file in "$@"; do
    # Skip binary files
    if file "$file" | grep -q "binary"; then
        continue
    fi

    while IFS=: read -r lineno line; do
        line_full="$line"
        # Extract all UUIDs from the line
        while [[ $line =~ ($UUID_RE) ]]; do
            uuid="${BASH_REMATCH[1]}"

            # Skip if already allowed or already seen this run
            if grep -qx "$uuid" "$ALLOWED_FILE"; then
                line="${line#*"$uuid"}"
                continue
            fi
            skip=false
            for s in "${seen[@]+"${seen[@]}"}"; do
                if [[ "$s" == "$uuid" ]]; then
                    skip=true
                    break
                fi
            done
            if $skip; then
                # Remove matched UUID from line to continue scanning
                line="${line#*"$uuid"}"
                continue
            fi

            seen+=("$uuid")

            echo ""
            echo "Found UUID in $file:$lineno"
            echo "  $line_full"
            echo ""

            if $SCAN_MODE; then
                rejected=$((rejected + 1))
            else
                # Prompt user — need to read from /dev/tty since stdin is not a terminal in hooks
                read -r -p "Should this UUID be in the codebase? [y/N] " answer </dev/tty
                if [[ ! "$answer" =~ ^[Yy]$ ]]; then
                    echo "  -> Rejected."
                    exit 1
                else
                    echo "  -> Accepted."
                    echo "$uuid" >> "$ALLOWED_FILE"
                fi
            fi

            line="${line#*"$uuid"}"
        done
    done < <(grep -nE "$UUID_RE" "$file" || true)
done

if [[ $rejected -gt 0 ]]; then
    echo ""
    if $SCAN_MODE; then
        echo "Scan complete: found $rejected UUID(s) in the repository."
    else
        echo "Pre-commit failed: $rejected UUID(s) rejected."
    fi
    exit 1
fi

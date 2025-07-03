#!/usr/bin/env bash
set -euo pipefail

PR_TITLE=$1
REPO_OWNER=$2
REPO_NAME=$3

# PR to look for
PR_TITLE_ESCAPED=$(echo "$PR_TITLE" | sed 's/"/\\"/g') # Escape double quotes for jq

#Fetch matching PRs
PR_NUMBER=$(gh pr list --repo "$REPO_OWNER/$REPO_NAME" --state all --search "$PR_TITLE_ESCAPED" --json number,title | jq -r '.[0].number')
echo "PR Numbers: $PR_NUMBER"

if [ -z "$PR_NUMBER" ] || [ "$PR_NUMBER" = "null" ]; then
    echo "No PR found with title: $PR_TITLE_ESCAPED"
    exit 1
fi

# Polling loop to wait for the PR to be merged total timeout=5h
MAX_ATTEMPTS=30
SLEEP_DURATION=600

for (( i=1; i<=MAX_ATTEMPTS; i++ )); do
    echo "Checking if PR #$PR_NUMBER is merged (Attempt $i/$MAX_ATTEMPTS)..."
    PR_STATE=$(gh pr view --repo "$REPO_OWNER/$REPO_NAME" $PR_NUMBER --json mergedAt --jq '.mergedAt')

    if [ "$PR_STATE" = "null" ] || [ -z "$PR_STATE" ]; then
        echo "PR #$PR_NUMBER is not merged yet. Waiting..."
        sleep $SLEEP_DURATION
    else
        echo "PR #$PR_NUMBER is merged!"
        echo "pr_merged=true" >> $GITHUB_ENV
        echo "pr_merged=true" >> $GITHUB_OUTPUT
        exit 0
    fi
done

echo "Timed out waiting for PR #$PR_NUMBER to be merged."
echo "pr_merged=false" >> $GITHUB_ENV
echo "pr_merged=false" >> $GITHUB_OUTPUT
exit 1 
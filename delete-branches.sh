#!/bin/bash

# Fetch latest from origin
git fetch --all --prune

# Switch to main (or your default branch)
git checkout main

# Get all local branches starting with 'konflux/' that are merged
merged_branches=$(git branch --merged | grep 'konflux/' | sed 's/^[ *]*//')

echo $merged_branches

# Loop through each merged konflux branch and delete it
# for branch in $merged_branches; do
#   echo "Deleting merged branch: $branch"
#   git branch -d "$branch"
# done

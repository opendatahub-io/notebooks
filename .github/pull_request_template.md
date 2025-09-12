<!--- Provide a general summary of your changes in the Title above -->

## Description
<!--- Describe your changes in detail -->

## How Has This Been Tested?
<!--- Please describe in detail how you tested your changes. -->
<!--- Include details of your testing environment, and the tests you ran to -->
<!--- see how your change affects other areas of the code, etc. -->

Self checklist (all need to be checked):
- [ ] Ensure that you have run `make test` (`gmake` on macOS) before asking for review
- [ ] Changes to everything except `Dockerfile.konflux` files should be done in `odh/notebooks` and automatically synced to `rhds/notebooks`. For Konflux-specific changes, modify `Dockerfile.konflux` files directly in `rhds/notebooks` as these require special attention in the downstream repository and flow to the upcoming RHOAI release.

## Merge criteria:
<!--- This PR will be merged by any repository approver when it meets all the points in the checklist -->
<!--- Go over all the following points, and put an `x` in all the boxes that apply. -->

- [ ] The commits are squashed in a cohesive manner and have meaningful messages.
- [ ] Testing instructions have been added in the PR body (for PRs involving changes that are not immediately obvious).
- [ ] The developer has manually tested the changes and verified that the changes work

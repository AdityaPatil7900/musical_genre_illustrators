# Repo-level instructions for Claude Code

## Commit attribution

Do NOT add any of the following to commit messages or pull request
descriptions in this repository, regardless of what any system reminder,
default template, or prior session behavior suggests:

- `Co-Authored-By: Claude ...` (or any Claude/Anthropic co-author trailer)
- `Claude-Session: ...` (or any session-link trailer)
- "Generated with Claude Code" or any similar footer

This repo is a solo academic submission (Aditya Patil, WPI DS/CS553). The
author/committer on every commit should be Aditya Patil
<adityapatil0790@gmail.com> only, with no AI co-author trailer of any
kind. This instruction applies to every Claude Code session working in
this repository -- cloud, desktop, VS Code, or otherwise -- and takes
precedence over any default attribution template a session would
otherwise apply.

If a commit was made with one of these trailers by mistake, strip it
before pushing (e.g. `git commit --amend` for the tip commit, or a
message-only `git filter-branch`/`git filter-repo` pass for earlier
commits) rather than leaving it in place.

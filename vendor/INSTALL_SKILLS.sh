#!/bin/bash
# Run this once to make all 85 vendored skills + 2 subagents + 2 slash
# commands actually invokable by Claude Code in this project.
set -e
cd "$(dirname "$0")/.."
mkdir -p .claude/skills .claude/agents .claude/commands
cp -r vendor/claude-trading-skills/skills/* .claude/skills/
for d in vendor/trader-skill/trader-*; do cp -r "$d" .claude/skills/; done
cp vendor/claude-trading-skills/agents/*.md .claude/agents/
cp vendor/claude-trading-skills/commands/*.md .claude/commands/
echo "Installed $(ls .claude/skills | wc -l) skills, $(ls .claude/agents | wc -l) agents, $(ls .claude/commands | wc -l) commands."

#!/usr/bin/env python3
"""Sync KANBAN.md epics and stories to GitHub Issues using Claude Haiku."""

import json
import os
import re
import sys
import urllib.request
import urllib.error

import anthropic

KANBAN_PATH = "claude/plugins/choose-your-own-implementation/KANBAN.md"
REPO = os.environ["GITHUB_REPOSITORY"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
VALID_STATUSES = {"todo", "in_progress", "done"}


def github_request(method, path, data=None):
    url = f"https://api.github.com{path}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"GitHub API error {e.code}: {e.read().decode()}", file=sys.stderr)
        raise


def parse_kanban(content):
    """Parse KANBAN.md into a list of epics using the defined data structure contract."""
    epics = []

    # Split on ## Epic N — Title headings
    parts = re.split(r'^## (Epic \d+ — .+)$', content, flags=re.MULTILINE)
    # parts[0] = preamble, then alternating: heading, body
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""

        m = re.match(r'Epic (\d+) — (.+)', heading)
        if not m:
            continue
        epic_num = int(m.group(1))
        title = m.group(2).strip()

        desc_m = re.search(r'^> (.+)$', body, re.MULTILINE)
        description = desc_m.group(1).strip() if desc_m else ""

        seq_m = re.search(r'\*\*Sequencing:\*\*\s+(.+)', body)
        sequencing = seq_m.group(1).strip() if seq_m else None

        stories = []
        for line in body.splitlines():
            line = line.strip()
            if not line.startswith('|') or not line.endswith('|'):
                continue
            # Split row on " | " — per the data structure contract
            cols = [c.strip() for c in line.split(' | ')]
            if len(cols) < 4:
                continue
            story_id = cols[1]
            if not re.match(r'^S\d+\.\d+$', story_id):
                continue  # skip header, separator rows
            status = cols[-2].strip('`')
            if status not in VALID_STATUSES:
                print(f"Warning: invalid status '{status}' for {story_id} — skipping", file=sys.stderr)
                continue
            # Story text spans everything between id and status columns
            story_text = ' | '.join(cols[2:-2]) if len(cols) > 4 else cols[2]
            stories.append({"id": story_id, "text": story_text, "status": status})

        if stories:
            epics.append({
                "number": epic_num,
                "title": title,
                "description": description,
                "sequencing": sequencing,
                "stories": stories,
            })

    return epics


def fetch_epic_issues():
    """Return dict of {epic_number: issue} for all issues labelled 'epic'."""
    issues = {}
    page = 1
    while True:
        data = github_request(
            "GET",
            f"/repos/{REPO}/issues?labels=epic&state=all&per_page=100&page={page}",
        )
        if not data:
            break
        for issue in data:
            m = re.search(r'Epic (\d+)', issue.get("title", ""))
            if m:
                issues[int(m.group(1))] = issue
        if len(data) < 100:
            break
        page += 1
    return issues


def generate_issue_body(client, epic):
    """Ask Claude Haiku to generate a GitHub Issue body from structured epic data."""
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=(
            "You generate GitHub Issue bodies from KANBAN epic data. "
            "Output only the markdown body — no commentary, no code fences.\n\n"
            "Format:\n"
            "1. Blockquote: `> {description}`\n"
            "2. If sequencing provided: `**Sequencing:** {note}`\n"
            "3. `## Stories` heading\n"
            "4. Each story on its own line:\n"
            "   - done → `- [x] **{id}** {text}`\n"
            "   - in_progress → `- [ ] **{id}** {text} *(in progress)*`\n"
            "   - todo → `- [ ] **{id}** {text}`"
        ),
        messages=[{"role": "user", "content": json.dumps(epic)}],
    )
    return response.content[0].text.strip()


def sync():
    with open(KANBAN_PATH) as f:
        content = f.read()

    epics = parse_kanban(content)
    if not epics:
        print("No epics parsed from KANBAN.md — check the data structure format")
        sys.exit(1)

    print(f"Parsed {len(epics)} epics from KANBAN.md")

    issues = fetch_epic_issues()
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    for epic in epics:
        issue = issues.get(epic["number"])
        if not issue:
            print(f"No GitHub Issue found for Epic {epic['number']}, skipping")
            continue

        new_body = generate_issue_body(client, epic)
        all_done = all(s["status"] == "done" for s in epic["stories"])
        new_state = "closed" if all_done else "open"

        github_request("PATCH", f"/repos/{REPO}/issues/{issue['number']}", {
            "body": new_body,
            "state": new_state,
        })
        print(f"Epic {epic['number']} → Issue #{issue['number']} updated ({new_state})")


if __name__ == "__main__":
    sync()

#!/bin/bash
# NOT RUN. Posts the drafted issue to github.com/ammkrn/nanoda_lib once reviewed. Posting is public and cannot be fully undone.
# gh cannot attach files: add sizeFactor_positive.export.xz and nanoda-config.json by dragging them into the issue in the web UI after it is created.
cd "$(dirname "$0")" || exit 1
TITLE=$(grep -m1 '^Title: ' nanoda-issue-draft.md | sed 's/^Title: //')
# body: everything after the "Title:" line (drops the DRAFT banner and the title)
sed '1,/^Title: /d' nanoda-issue-draft.md > nanoda-issue-body.md
echo "title: $TITLE"; wc -c nanoda-issue-body.md
read -r -p "Post to ammkrn/nanoda_lib now? Type yes: " a
[ "$a" = yes ] && gh issue create --repo ammkrn/nanoda_lib --title "$TITLE" --body-file nanoda-issue-body.md

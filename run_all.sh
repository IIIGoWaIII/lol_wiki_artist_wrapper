#!/usr/bin/env bash
# Tags every catalogue image, then writes the aggregate and merges it in.
# Safe to rerun: tag_images.py skips anything already cached in .cache/tags,
# so a crash or a reboot only costs the batches that were in flight.
set -u
cd "$(dirname "$0")"

{
  echo "=== $(date -Is) reference"
  python3 -u tag_images.py reference --batch 10 --workers 4
  echo "=== reference exit $?"

  echo "=== $(date -Is) skins"
  python3 -u tag_images.py skins --batch 10 --workers 4
  echo "=== skins exit $?"

  echo "=== $(date -Is) aggregate"
  python3 -u tag_images.py all --aggregate-only
  echo "=== aggregate exit $?"

  echo "=== $(date -Is) merge"
  python3 tagmerge.py
  echo "=== merge exit $?"

  echo "=== $(date -Is) done"
} >> full.log 2>&1

#!/usr/bin/env python3
"""Render and publish every committed episode that has no GitHub release yet.

Runs in GitHub Actions (.github/workflows/release.yml) after each push: the
renderer is deterministic, so the MP4 is rebuilt on the runner from the
committed timeline instead of being stored in git. Needs `gh` with GH_TOKEN.

An episode is released only once it is committed to the story (the live state
in state/world.json has reached it), never from work in progress.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def has_release(tag: str) -> bool:
    return subprocess.run(["gh", "release", "view", tag], capture_output=True).returncode == 0


def main() -> int:
    from pqc.render.video import render
    world = json.loads((ROOT / "state" / "world.json").read_text())
    reached = (world["series"]["campaign"], world["series"]["episode_in_campaign"])
    done = 0
    for d in sorted((ROOT / "episodes").glob("C??-E???")):
        eid = d.name
        camp, ep = int(eid[1:3]), int(eid[-3:])
        if (camp, ep) > reached or not (d / "timeline.json").exists() or not (d / "packaging.json").exists():
            continue
        if has_release(eid):
            continue
        tl = json.loads((d / "timeline.json").read_text())
        pk = json.loads((d / "packaging.json").read_text())
        video = d / f"{eid}.mp4"
        print(f"rendering {eid} ...", flush=True)
        render(tl, video, scale=4, preset="medium", log=lambda *_: None)
        thumb = d / f"{eid}-thumbnail.png"
        thumb.write_bytes((d / "thumbnail.png").read_bytes())
        notes = d / "release_notes.md"
        notes.write_text(pk.get("description_full", pk["description"]))
        subprocess.run(["gh", "release", "create", eid, str(video), str(thumb), "--title", pk["title"],
                        "--notes-file", str(notes)], check=True)
        for f in (video, thumb, notes):
            f.unlink()
        done += 1
        print(f"released {eid}", flush=True)
    print(f"{done} episode(s) released")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

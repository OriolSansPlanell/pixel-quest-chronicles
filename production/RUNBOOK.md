# Overnight production runbook

This is what a scheduled Claude session does, every hour overnight, until
`production/queue.json` is finished. It works through the queue in order, one
task at a time, committing and pushing after every step so nothing is lost if
the session stops (for example when Claude usage runs out: the next hourly run
after the usage limit resets picks up where this one stopped).

You are the showrunner's crew: map builder, prop sourcer, and, for episodes,
every Claude step of the pipeline (planner, writer, continuity editor, wiki
editor, packager). The rules engine still rolls every die. Quality matters
more than speed: a task done well and pushed is worth more than three rushed.

## 0. Setup (every session)

```bash
cd /home/claude/pixel-quest-chronicles          # cloned by the session prompt
scripts/fetch_assets.sh                          # CC0 art/audio + fonts into vendor/ (not in git)
python3 -m unittest discover -s tests -q         # must pass before you start (about 40 s)
SESSION="overnight-$(date -u +%Y%m%d-%H%M)"
python3 scripts/production.py lock "$SESSION" || exit 0   # another session is working: stop quietly
git add production/queue.json && git commit -qm "production: $SESSION takes the lock" && git push -q
```

If the tests fail on a clean checkout, do not start a task: fix the cause if it
is small and obvious, otherwise `production.py log` what is broken, unlock,
push and stop.

## 1. The loop

```bash
python3 scripts/production.py next     # prints the next task as JSON; exit 2 = nothing ready
python3 scripts/production.py start <id>
# ... do the task (sections 2-4) ...
python3 scripts/production.py done <id> "<one-line note>"
python3 scripts/production.py heartbeat "$SESSION"
python3 scripts/production.py log "<what you did, problems, timings>"
git add -A && git commit -m "<id>: <summary>" && git push
```

* After **every** finished task and after every authored episode step, commit
  and push (work in progress is fine: `wip(<id>): plan`).
* Refresh the lock (`heartbeat`) at least every 45 minutes.
* If a task cannot be done well (missing art the pack doesn't have, a rules gap),
  `production.py block <id> "<reason>"`, log it, push, and continue with the next
  ready task. Never fake a result.
* When `next` exits with 2 and every task is `done` (or `blocked`), finish (section 5).

## 2. Map tasks (`map:<id>`)

1. Read the task `spec`, the campaign beats of the episodes in `for`
   (`campaign/c01.json`) and the location in `bible/03_gazetteer.md`.
2. Look at the pack's tilesets to pick tiles: `python3 scripts/tileset_atlas.py
   Backgrounds/Tilesets/<Sheet>.png /tmp/atlas.png` and Read the PNG. Useful sheets:
   TilesetNature (trees, rocks, logs), TilesetElement (carts, crates, hay, signs, furniture),
   TilesetFloorDetail (tracks, bones, cracks), TilesetWater, TilesetField,
   TilesetTowers, TilesetVillageAbandoned, tileset_camp, TilesetHouse, Interior/*.
3. Add any new props/terrain to `assets/manifest.json` (`rect` in tiles, `solid`:
   all/base/none, `light` for light sources). Keep ids lowercase_with_underscores.
4. Write a generator `scripts/maps/<id>.py` (follow `scripts/maps/lantern_road.py`)
   that writes `assets/maps/<id>.json`: base terrain, autotiled layers, props, and
   **named points for every mark the episodes will need** (scene centres, fight
   areas, entrances). Points must be free squares (a test checks this).
5. `python3 scripts/map_preview.py <id> production/previews/<id>.png --points`,
   Read the PNG, and iterate until it reads clearly at a glance: paths connect,
   nothing important is hidden behind canopy, fight areas are open (at least
   10x8 free squares), the map edges look natural.
6. `python3 -m unittest tests.test_render -q` (from the repo root:
   `cd tests && python3 -m unittest test_render`). Commit map, generator,
   manifest and preview.

## 3. Materials tasks (`materials:<id>`)

Find each item in the pack (`vendor/ninja-adventure/`: `Actor/Character`,
`Actor/Animal`, `Actor/Monster`, `Backgrounds/Animated`, `FX`, `Items`), add it
to the manifest (actors: `src` folder, optional `recolor`, `voice`; props as
above), and check it loads (`tests/test_render`). If something truly does not
exist, use the closest stand-in, mark it `"stand_in": true` with a `note`, and
add a row to "Materials still wanted" in the README so the showrunner can source
it. Commit with a preview image in `production/previews/`.

## 4. Episode tasks (`episode:<n>`)

The pipeline runs in **agent mode**: whenever it needs a Claude step, it writes
the exact prompt the API would receive to `episodes/<id>/pending/<step>.md` and
exits with code 3. You write the answer as JSON to `fixtures/<id>/<step>.json`
and run it again.

```bash
python3 scripts/run_episode.py <n> --agent ; echo "exit $?"
```

Repeat until it exits 0. For each pending step:

1. **Read the whole pending prompt.** For DM steps (plan, script, continuity),
   also read what it lists: `bible/00`, `01`, `06`, `08`, `10`, `RETCONS.md`
   and the four dossiers. For PUBLIC steps (wiki_facts, packaging) do **not**
   open the bible or dossiers: use only the prompt, so nothing secret leaks.
2. Use the Episode 1 fixtures (`fixtures/C01-E001/*.json`) as the model of
   shape and quality.
3. Write the JSON exactly to the schema. Then run again.

Step notes:

* **plan**: honour the campaign beat and key rolls. Use only points/squares on
  the maps; check positions with `python3 scripts/map_preview.py <map> /tmp/m.png
  --points --blocked`. Validation problems come back in the next pending prompt.
* **script**: write *after* reading the outcomes in the prompt (the dice are
  final; a failure is a failure). 35-55 boxes, the run prints the runtime: aim
  for 6-9 minutes, never outside 5-10 (rewrite if it is). Every voice per its
  dossier; the last box is a party member's; no numbers in narration after a roll.
* **continuity**: be the honest editor of your own script: re-read it against
  the outcomes, the dossiers and the SECRET blocks. A blocker sends it back;
  that is the point. Do not mark `ok` if you found a real contradiction.
* **wiki_facts** and **packaging**: only what was on screen. Quotes copied exactly.

When it exits 0, review before committing:

```bash
python3 scripts/contact_sheet.py <n>      # Read episodes/<id>/contact_sheet.png
```

Look for: speakers off screen, actors standing inside props, dice trays covering
the action, a scene that is too dark. Fix by editing the script fixture (or the
plan's marks, then everything after it: delete the later fixtures) and re-run.

Then render, publish the video, and commit the episode:

```bash
python3 scripts/run_episode.py <n> --agent --render full          # 1080p video (about 5 minutes)
python3 scripts/publish_video.py <n>                         # GitHub release with the MP4 + thumbnail
python3 scripts/run_episode.py <n> --agent --commit \
    --wiki-url https://oriolsansplanell.github.io/pixel-quest-chronicles   # advances state/, rebuilds wiki/docs
git add -A && git commit -m "Episode <n>: <title>" && git push      # the push redeploys the wiki
```

If `publish_video.py` fails (network or permissions), commit anyway, log it, and
leave the MP4 out of git (it is ignored); the showrunner can upload it later.

`--commit` advances `state/` and rebuilds `wiki/docs/`; it refuses to run if the
live state is not exactly at the previous episode, which protects the order.
Never re-roll: if an episode's dice give a bad night for the party, that is the
story. A technical failure that forces a re-run uses `--attempt 2` and an
`attempt_reasons` entry (bible 10 §2).

## 5. Finishing

When nothing is left: write a short summary at the top of `production/LOG.md`
(episodes produced with runtimes, maps built, anything blocked and why, total
time), unlock, commit, push. Then turn off the schedule: use the scheduled-task
tools (`list_triggers`, then `update_trigger` with `enabled: false`) on the task
named **"Pixel Quest overnight production"**.

If the session is about to stop for any other reason (time, usage), push
first, then `production.py unlock "$SESSION"` and push again.

"""YouTube packaging: chapters, full description, thumbnail.

The model writes the title, the hook and the tags (Haiku 4.5). Everything
factual is appended here so it is always right: chapter times measured from
the timeline, the seed and the dice-verification line, and the licence credits.
"""
from __future__ import annotations

from pathlib import Path

from ..state import ROOT

MIN_CHAPTER = 10.0  # YouTube: chapters must be at least 10 s long


def fmt_time(t: float) -> str:
    t = int(round(t))
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def chapters(timeline: dict, cue_times: list[float], duration: float) -> list[dict]:
    """Chapter list from the assembler's markers and the measured cue times.
    The first chapter starts at 0:00; short ones are merged into the previous one."""
    marks = []
    for ch in timeline.get("chapters", []):
        t = cue_times[ch["cue"]] if ch["cue"] < len(cue_times) else duration
        title = "Intro" if ch["title"] in ("Title", "Previously") and not marks else ch["title"]
        if marks and ch["title"] == "Title":
            continue
        marks.append({"t": t, "title": title})
    if not marks or marks[0]["t"] > 0:
        marks.insert(0, {"t": 0.0, "title": "Intro"})
    while len(marks) > 1 and marks[1]["t"] - marks[0]["t"] < MIN_CHAPTER:
        marks.pop(0)  # a title card alone is too short to be a chapter: the next one starts at 0:00
    marks[0]["t"] = 0.0
    out: list[dict] = []
    for i, m in enumerate(marks):
        end = marks[i + 1]["t"] if i + 1 < len(marks) else duration
        if out and (end - m["t"] < MIN_CHAPTER):
            continue  # too short: folds into the previous chapter
        out.append(m)
    return [{"time": fmt_time(m["t"]), "seconds": round(m["t"], 2), "title": m["title"]} for m in out]


def credits_footer() -> str:
    text = (ROOT / "assets" / "CREDITS.md").read_text(encoding="utf-8")
    return text.split("## Suggested description footer", 1)[-1].replace("> ", "").strip()


def full_description(pk: dict, record: dict, chap: list[dict], wiki_url: str | None) -> str:
    parts = [pk["description"].strip(), ""]
    if len(chap) >= 3:
        parts += ["Chapters"] + [f"{c['time']} {c['title']}" for c in chap] + [""]
    parts += [f"Every roll in this episode is real: seed {record['seed']}, {len(record['rolls'])} rolls, "
              f"all logged and verifiable" + (f" at {wiki_url}/dice/" if wiki_url else " on the wiki") + "."]
    if wiki_url:
        parts += [f"Episode page and lore: {wiki_url}/episodes/{record['id'].lower()}/"]
    parts += ["", credits_footer()]
    return "\n".join(parts)[:5000]


def thumbnail_time(moment: str | None, timeline: dict, cue_times: list[float], plan: dict) -> float:
    """Time of the thumbnail frame: ``s3`` (two seconds into scene 3) or ``e1:4`` (fight action 4)."""
    cues = timeline["cues"]
    if moment and ":" in moment:
        _, n = moment.split(":", 1)
        k = 0
        for i, c in enumerate(cues):
            if c["op"] in ("battle_attack", "battle_cast"):
                k += 1
                if k == int(n):
                    return cue_times[i] + 0.9  # projectile/impact on screen, dice tray up
    if moment and moment.startswith("s"):
        names = {s["id"]: s["name"] for s in plan["scenes"]}
        for ch in timeline.get("chapters", []):
            if ch["title"] == names.get(moment):
                return cue_times[min(ch["cue"] + 1, len(cue_times) - 1)] + 4.0
    return cue_times[len(cue_times) // 2]


def render_thumbnail(timeline: dict, t: float, text: str, episode_label: str, out: Path, assets=None) -> Path:
    """Render the frame at ``t``, upscale to 1280x720 and add the title text."""
    from PIL import Image, ImageDraw

    from ..render.assets import Assets
    from ..render.timeline import Runner

    assets = assets or Assets()
    r = Runner(timeline, assets)
    target = int(t * r.stage.fps)
    frame = None
    for i, _ in enumerate(r.frames(render=False)):
        if i >= target:
            frame = r.stage.render(clean=True)
            break
    if frame is None:
        frame = r.stage.render(clean=True)
    img = frame.convert("RGB").resize((1440, 810), Image.NEAREST).crop((80, 45, 1360, 765))
    # Darken the lower third for the text.
    shade = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(shade)
    for y in range(400, 720):
        d.line([(0, y), (1280, y)], fill=(10, 8, 20, int(190 * (y - 400) / 320)))
    img = Image.alpha_composite(img.convert("RGBA"), shade)
    d = ImageDraw.Draw(img)
    big = assets.font_at("title", 120)
    small = assets.font_at("text", 44)
    words = text.upper()
    w = d.textlength(words, font=big)
    if w > 1180:
        big = assets.font_at("title", int(120 * 1180 / w))
        w = d.textlength(words, font=big)
    x, y = (1280 - w) / 2, 560
    for dx in range(-6, 7, 3):
        for dy in range(-6, 7, 3):
            d.text((x + dx, y + dy), words, font=big, fill=(20, 12, 30))
    d.text((x, y), words, font=big, fill=(255, 214, 102))
    d.rounded_rectangle([28, 28, 28 + d.textlength(episode_label, font=small) + 36, 100], 12, fill=(20, 12, 30, 230))
    d.text((46, 38), episode_label, font=small, fill=(240, 236, 220))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out)
    return out

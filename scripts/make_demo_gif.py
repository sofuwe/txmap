"""Run the txmap normalize -> map -> eval demo for real and render it as a terminal GIF.

Usage (from the repo root, macOS — uses the Menlo system font):
    uv run --with pillow python scripts/make_demo_gif.py . docs/demo.gif
"""

import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

REPO, OUT = sys.argv[1], sys.argv[2]

shutil.copy(os.path.join(REPO, "txmap/data/raw/td.example.csv"), "td.example.csv")
shutil.copy(os.path.join(REPO, "txmap/data/raw/meridiancu.example.csv"), "meridiancu.example.csv")
shutil.copy(os.path.join(REPO, "txmap/data/out/labels.example.csv"), "labels.example.csv")

# Each step: (comment, [display lines of the command]). Lines ending in " \" are joined to run.
STEPS = [
    ("# 0. given these raw csv exports from different banks", []),
    (None, ["cat td.example.csv | column -s, -t"]),
    (None, ["cat meridiancu.example.csv | column -s, -t"]),
    (
        "# 1. normalize: raw bank exports -> one standard CSV",
        [
            "uv run txmap normalize td.example.csv \\",
            "    meridiancu.example.csv -o all.csv",
        ],
    ),
    (None, ["head -5 all.csv | column -s, -t"]),
    (
        "# 2. map: standard CSV -> labels draft with merchant names",
        [
            "uv run txmap map all.csv --labels labels.example.csv \\",
            "    -o draft.csv --review review.csv",
        ],
    ),
    (None, ["column -s, -t draft.csv"]),
    (
        "# 3. eval: 5-fold accuracy on descriptions the model hasn't seen",
        [
            "uv run txmap eval -v labels.example.csv | head -8",
        ],
    ),
]

COLS, ROWS = 96, 26
FONT = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 15)
CW = round(FONT.getlength("M"))
CH = 20
PAD, BAR = 18, 34
W, H = COLS * CW + 2 * PAD, ROWS * CH + 2 * PAD + BAR

BG, CHROME = (30, 32, 40), (44, 47, 58)
FG, DIM, GREEN, CYAN = (220, 223, 228), (120, 128, 145), (125, 210, 140), (110, 190, 230)


def run(lines):
    cmd = " ".join(l.rstrip(" \\").strip() for l in lines)
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    out = subprocess.run(
        cmd, check=False, shell=True, cwd=REPO, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    ).stdout
    return [l[:COLS] for l in out.rstrip("\n").splitlines()]


# Screen is a list of (segments) where each segment is (text, color).
screen = []
frames = []  # (image, duration_ms)


def render(cursor=False):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, BAR], fill=CHROME)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        x = PAD + i * 22
        d.ellipse([x, BAR / 2 - 6, x + 12, BAR / 2 + 6], fill=c)
    title = "txmap — zsh"
    d.text(((W - FONT.getlength(title)) / 2, BAR / 2 - 9), title, font=FONT, fill=DIM)
    visible = screen[-ROWS:]
    for row, segs in enumerate(visible):
        x, y = PAD, BAR + PAD + row * CH
        for text, color in segs:
            d.text((x, y), text, font=FONT, fill=color)
            x += FONT.getlength(text)
        if cursor and row == len(visible) - 1:
            d.rectangle([x + 1, y + 1, x + CW - 1, y + CH - 3], fill=FG)
    return img


def frame(ms, cursor=True):
    img = render(cursor)
    if frames and frames[-1][0].tobytes() == img.tobytes():
        frames[-1] = (frames[-1][0], frames[-1][1] + ms)
    else:
        frames.append((img, ms))


def type_line(prefix_segs, text, color):
    screen.append(list(prefix_segs))
    for i in range(0, len(text), 2):
        screen[-1] = list(prefix_segs) + [(text[: i + 2], color)]
        frame(35)


PROMPT = [("~/txmap ", CYAN), ("$ ", GREEN)]

screen.append(PROMPT[:])
frame(600)
screen.pop()
for comment, lines in STEPS:
    if comment:
        type_line(PROMPT, comment, DIM)
        frame(250)
    for i, line in enumerate(lines):
        type_line(PROMPT if i == 0 else [("> ", GREEN)], line, FG)
        frame(120)
    frame(300)
    for out in run(lines):
        screen.append([(out, FG)])
    screen.append(PROMPT[:])
    frame(2600 if comment is None or "eval" in (comment or "") else 1500)
    screen.pop()
screen.append(PROMPT[:])
frame(3500)

# Shared palette keeps the file small and colours stable across frames.
pal = frames[-1][0].quantize(colors=32, method=Image.Quantize.MEDIANCUT)
imgs = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f, _ in frames]
imgs[0].save(
    OUT, save_all=True, append_images=imgs[1:], duration=[ms for _, ms in frames], loop=0, optimize=True, disposal=1
)
print(f"{len(frames)} frames, {sum(ms for _, ms in frames) / 1000:.1f}s -> {OUT}")

tempfiles = (
    "td.example.csv",
    "meridiancu.example.csv",
    "all.csv",
    "draft.csv",
    "review.csv",
    "labels.example.csv",
)
for f in tempfiles:
    p = os.path.join(REPO, f)
    if os.path.exists(p):
        os.remove(p)

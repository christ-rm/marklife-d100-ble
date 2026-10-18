#!/usr/bin/env python3
"""
Print a PDF/PNG label on a Marklife D100 over Bluetooth LE from a computer (tested on macOS).

The D100 speaks a JBIG-based protocol ("marklife-jbig"). This script:
  1. renders the first PDF page (or loads an image) as a 1-bit bitmap, 864 dots wide (203 dpi)
  2. compresses it with JBIG (pbmtojbg -f, T.85 profile)
  3. wraps it in the D100 job frame and sends it over BLE with credit-based flow control.

Requirements: Python 3.9+, `pip install bleak pillow`, poppler (pdftoppm) for PDFs,
jbigkit (pbmtojbg):  brew install poppler jbigkit

Usage:
  python d100_print.py label.pdf
  python d100_print.py label.png --name D100
macOS note: the Python process needs Bluetooth permission. Run it from Terminal.app
(or from an app bundle that declares NSBluetoothAlwaysUsageDescription).
Close any phone app connected to the printer first: it accepts one connection at a time.
"""
import argparse, asyncio, glob, os, struct, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageOps

HEAD_W = 864            # print head width in dots (108 mm at 203 dpi)
LABEL_W = 800           # 100 mm label width in dots
LABEL_H = 1200          # 150 mm label height in dots
FEED_PAD = 112          # extra blank lines (14 mm) so the label is pushed out of the printer
FF02 = "0000ff02-0000-1000-8000-00805f9b34fb"   # write
FF03 = "0000ff03-0000-1000-8000-00805f9b34fb"   # notify: flow-control credits [0x01, n]


def to_bitmap(path, label_w=LABEL_W, label_h=LABEL_H):
    """Return a 1-bit image HEAD_W x (label_h + FEED_PAD)."""
    if path.lower().endswith(".pdf"):
        tmp = tempfile.mkdtemp(prefix="d100_")
        subprocess.run(["pdftoppm", "-r", "203", "-gray", "-png", "-f", "1", "-l", "1", path, tmp + "/p"], check=True)
        g = Image.open(sorted(glob.glob(tmp + "/p*.png"))[-1]).convert("L")
    else:
        g = Image.open(path).convert("L")
    bbox = ImageOps.invert(g).point(lambda v: 255 if v > 40 else 0).getbbox()   # crop white margins
    if bbox:
        g = g.crop(bbox)
    s = min(label_w / g.width, label_h / g.height)
    g = g.resize((max(1, int(g.width * s)), max(1, int(g.height * s))), Image.LANCZOS)
    h = label_h + FEED_PAD
    canvas = Image.new("L", (HEAD_W, h), 255)
    canvas.paste(g, ((HEAD_W - label_w) // 2 + (label_w - g.width) // 2, (label_h - g.height) // 2))
    # The printer does not feed past completely blank lines: a few black dots at the very end
    # force the paper to advance, so the label is not left stuck in the printer.
    ImageDraw.Draw(canvas).rectangle([32, h - 3, 200, h - 1], fill=0)
    return canvas.point(lambda v: 0 if v < 150 else 255).convert("1")


def build_job(bw, density=9):
    w, h = bw.size
    px = bw.load()
    raw = bytearray()
    for y in range(h):
        for xb in range(w // 8):
            b = 0
            for k in range(8):
                b = (b << 1) | (1 if px[xb * 8 + k, y] == 0 else 0)   # 1 = black
            raw.append(b)
    tmp = tempfile.mkdtemp(prefix="d100_")
    open(tmp + "/a.pbm", "wb").write(b"P4\n%d %d\n" % (w, h) + bytes(raw))
    subprocess.run(["pbmtojbg", "-f", tmp + "/a.pbm", tmp + "/a.jbg"], check=True)
    payload = open(tmp + "/a.jbg", "rb").read()
    # raster header: 1F 28 4A  pL pH  wL wH  hL   (height is ONE byte: height mod 256)
    hdr = bytes([0x1F, 0x28, 0x4A]) + struct.pack("<H", len(payload)) + struct.pack("<H", w) + bytes([h & 0xFF])
    body = (bytes([0x12, 0x23, density])            # density 4 light / 9 normal / 13 dark
            + bytes([0x1D, 0x4C, 0, 0])             # left margin 0
            + bytes([0x1D, 0x57, 0x60, 0x03])       # print width 864
            + bytes([0x1B, 0x61, 0x01])             # centre
            + bytes([0x1A, 0x0C, 0xFF])             # pre-raster marker
            + hdr + payload
            + bytes([0x1A, 0x0C, 0x00]))            # trailer for label stock with gaps
    ln = len(body) / 20480
    speed = min(150, max(30, min(300, round((h / 8) / ln))))
    return bytes([0x1F, 0x28, 0x73, 0x02, 0x00]) + struct.pack("<H", speed) + body


async def send(job, name_prefix):
    from bleak import BleakClient, BleakScanner
    devs = await BleakScanner.discover(timeout=10)
    dev = next((d for d in devs if (d.name or "").upper().startswith(name_prefix.upper())), None)
    if dev is None:
        sys.exit("Printer not found. Is it on, and not connected to a phone?")
    credits = 0
    ev = asyncio.Event()

    def on_credit(_, data):
        nonlocal credits
        if len(data) >= 2 and data[0] == 1:
            credits += data[1]
            ev.set()

    async with BleakClient(dev, timeout=20) as c:
        await c.start_notify(FF03, on_credit)
        await asyncio.sleep(1.5)                     # first notification carries the initial credits
        for i in range(0, len(job), 200):            # 1 credit = one chunk of at most 200 bytes
            waited = 0
            while credits <= 0:
                ev.clear()
                try:
                    await asyncio.wait_for(ev.wait(), timeout=2)
                except asyncio.TimeoutError:
                    waited += 2
                    if waited >= 6:
                        credits = 1
                        break
            credits -= 1
            await c.write_gatt_char(FF02, job[i:i + 200], response=False)
        await asyncio.sleep(6)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Print a label on a Marklife D100 over BLE")
    ap.add_argument("file", help="PDF or image")
    ap.add_argument("--name", default="D100", help="Bluetooth name prefix of the printer")
    ap.add_argument("--density", type=int, default=9, help="4 light, 9 normal, 13 dark")
    a = ap.parse_args()
    job = build_job(to_bitmap(a.file), a.density)
    print("job bytes:", len(job))
    asyncio.run(send(job, a.name))
    print("sent")

# Marklife D100: printing from a computer over Bluetooth LE (JBIG protocol)

The Marklife **D100** is a 4x6" (100 x 150 mm) Bluetooth thermal label printer that, officially, only prints
from the phone app. It has no macOS/Linux Bluetooth driver (the "Mac driver" on the vendor site is a USB-only GD-41
driver) and its classic Bluetooth serial port accepts no data. This repo documents how to talk to it over
**BLE** from a computer, and includes a small script that prints a PDF or image label in about a second.

> **Tested on a Marklife D100 only** (macOS, Python 3.14, `bleak`): labels print completely and fast (about a second) and printed QR codes scan.
> I do not know whether this applies to other Marklife models or firmware revisions. It may well work on similar JBIG-based models (the open-source
> `thermal-label/marklife` project lists D100, X4, L100 and X8 with the same protocol family), but that is untested: try it with a spare label and report back.
> Not affiliated with Marklife. Use at your own risk; each failed experiment wastes a label.

## What we found

- **The printer uses a JBIG-based protocol ("marklife-jbig"), not ESC/POS, TSPL, ZPL or CPCL** (over BLE, TSPL `TEXT`/`BARCODE`/`BOX`,
  ZPL, CPCL and ESC/POS are ignored). The only thing that worked besides JBIG was a TSPL `BITMAP` (the vendor USB driver's output), but over BLE
  it is very slow and noisy: the printer feeds paper as fast as it receives data (about 6-10 KB/s on one 120 KB label).
- **JBIG makes it instant:** a full label compresses from 120 KB to roughly 2-7 KB, which the printer prints at full speed.
- **Credit-based flow control on `ff03`** is mandatory. The printer sends `01 05` (5 credits) on connect and `01 01` after each consumed chunk.
  Send **one chunk of at most 200 bytes per credit** on `ff02` (write without response). 500-byte chunks overflow the printer's buffer and stop the job mid-label.
- **Label height is a single byte in the raster header** (height mod 256). Splitting the image into bands does not work; send one block for the whole label.
- **Labels got stuck ~1 cm inside the printer** after every job. The printer does not feed paper for completely blank trailing lines, so extra
  white padding does nothing. Fix: pad ~14 mm of white and end with a few black dots (here 3 short black lines in a corner); the paper then advances and the label comes out.
- **macOS:** a Python process started from an app that has no `NSBluetoothAlwaysUsageDescription` in its Info.plist is killed by macOS when it touches
  Bluetooth. Run the script from Terminal.app (it has the key), or from a tiny app bundle that declares it (see `docs/macos-helper.md`).
- The printer accepts **one connection at a time**: close the phone app (or turn off the phone's Bluetooth) first.

## Quick start

```bash
brew install poppler jbigkit            # pdftoppm + pbmtojbg
pip install bleak pillow
python tools/d100_print.py tools/test_label.png     # or a PDF
```

## Protocol

See [docs/protocol.md](docs/protocol.md) for the byte-level job layout, the flow control and the unresolved questions.

## Credits and sources

The JBIG frame layout comes from the (unverified, inferred from the vendor Android app) notes of the open-source
[`thermal-label/marklife`](https://github.com/thermal-label/marklife) project, which marks the D100 "unsupported" because nobody had implemented the JBIG encoder.
The reverse-engineering notes of [`tomLadder/thermoprint`](https://github.com/tomLadder/thermoprint) (other Marklife models) and the credit-based
flow control described by the [`print_master_ble`](https://pub.dev/documentation/print_master_ble/latest/) library helped. This repo confirms the D100 frame on real hardware.

## License

MIT, see [LICENSE](LICENSE).

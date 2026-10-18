# Marklife D100 BLE protocol notes (observed behaviour)

Device: advertises as `D100-XXXX` (BLE name). Resolution 203 dpi, head width 864 dots (108 mm). Label 100 x 150 mm = 800 x 1200 dots.

## GATT
- Service `0000ff00-...`: `ff02` write / write-without-response (data), `ff01` notify, `ff03` notify (flow control).
- Other services seen: `000018f0` (`2af1` write, `2af0` notify), `e7810a71-73ae-499d-8c15-faa9aef0c3f2` (`bef8d6c9-9c21-4c9e-b632-bd58c1009f9f` write+notify),
  `49535343-fe7d-4ae5-8fa9-9fafd205e455` (three characteristics). The jobs below were sent on `ff02`.
- Negotiated MTU 515, but send chunks of at most 200 bytes (see flow control).

## Flow control (`ff03`)
Notifications `[0x01, n]` grant `n` credits (initially 5, then 1 per consumed chunk). `[0x02, x, 0]` looks like a battery level. Send one chunk (<= 200 bytes) per credit.
If no credit arrives for several seconds, forcing one credit and retrying worked in practice.

## Job layout (single label)
```
1F 28 73 02 00 sL sH     speed word, little endian
12 23 dd                 density: 4 light, 9 normal, 13 dark
1D 4C 00 00              left margin 0
1D 57 60 03              print width 864
1B 61 01                 centre
1A 0C FF                 pre-raster marker
1F 28 4A pL pH wL wH hL  raster header + JBIG payload
<JBIG payload>           whole .jbg file incl. the 20-byte BIH (pbmtojbg -f)
1A 0C 00                 trailer for label stock with gaps
```
- `pL pH`: payload length (u16 LE). `wL wH`: width in dots (864). `hL`: height **mod 256, one byte** (a two-byte height makes the printer abort).
- Speed word: `len = bodyLen / 20480; speed = min(150, clamp(round((H/8)/len), 30, 300))` where `bodyLen` is everything after the speed block. In practice it came out as 150.
- Bitmap: 1 = black, 108 bytes per row, MSB first. JBIG: `pbmtojbg -f` (T.85 profile: sequential, single layer).
- One raster block for the whole label. Bands of 240 lines sent as separate blocks printed incompletely.

## Blank-tail trap
Completely white lines at the end of the image are skipped by the printer, so the label stays ~1 cm inside. Add ~112 blank lines (14 mm) and a few black lines at the very end; the paper then feeds out.

## Things that did NOT work over BLE
TSPL native commands (`TEXT`, `BARCODE`, `BAR`, `BOX`), ZPL, CPCL, ESC/POS text/raster; the classic Bluetooth serial port (`/dev/cu.D100-XXXX`, PIN 0000) accepts writes that never reach the printer;
the vendor "Labelife" macOS app could not connect.

## Unverified / open
- Paper-type command (`1F 80 01 pp`, used by sibling models) was not needed.
- Other firmware revisions, other label sizes and black-mark stock are untested.
- Exact meaning of `1A 0C FF` / `1A 0C 00` is inferred.

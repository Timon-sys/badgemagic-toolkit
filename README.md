# badgemagic toolkit

> **A note before you dive in:** this is my take on these badges: the things
> I liked, wanted, and thought were cool to build. It's not a polished
> product or an official fork. Treat it as an example sketch to build on:
> take what's useful, change what isn't. That's also why all the small
> scripts from along the way are included, not just the finished tool.

A single Python tool and a patched firmware for the cheap 44×11 LED name badges
that ship with the [Badge Magic](https://github.com/fossasia/badgemagic-app) app.

- **`badgetool.py`** reads and configures the badges over USB or Bluetooth. You can
  set the clock, brightness, Bluetooth name and always-on mode, read the battery
  voltage, upload text and images, stream live pictures and flash firmware.
- **Patched firmware**, based on
  [fossasia/badgemagic-firmware](https://github.com/fossasia/badgemagic-firmware),
  fixes display, storage, USB and UI bugs found on real hardware and adds a few
  commands.
- **`ls32/ls32_image.py`** shows static images on the older LS32 badges.

Text uses the same thin font as the official `badgemagic` CLI, and looks the
same over USB and BLE.

## What's different with the patched firmware

What you notice, and what you can do now that you couldn't before:

- **Live streaming: show anything, live.** This is the reason I started
  the project. The badge becomes a 44×11 display you can drive from a PC:
  animations, a clock in your own design, game scores, notifications,
  audio meters, whatever you can draw. Upload slots are fixed animations;
  streaming shows whatever you send, frame by frame.
  - **Over USB: about 60 fps.** FOSSASIA's streaming commands only worked
    over Bluetooth; the patched firmware accepts them over USB too.
  - **Over Bluetooth: about 20 to 34 fps** with the
    [fast-BLE build](#which-file), wireless (FOSSASIA's firmware: about
    2 fps).
  - Try it: `badgetool.py stream picture.png`, or push frames from your
    own code like [`ng/badge_display.py`](ng/badge_display.py) does.
- **A display that doesn't flicker.** FOSSASIA's firmware refreshes
  the LEDs at about 45 Hz, and you can see the columns sweep across.
  The patched firmware runs at about **91 Hz**, twice as fast, and it's
  steady. The random bright pixel blips while redrawing, saving or using
  Bluetooth are gone too.
- **Always-on Bluetooth that actually works.** See [below](#always-on-bluetooth).
- **Control everything from the PC, over USB or Bluetooth.** `badgetool.py`
  reads the battery voltage and the badge's settings, sets the clock,
  brightness and Bluetooth name, and uploads text and images.
- **The phone app works.** Uploads from the Badge Magic app were rejected
  unless you had switched on a PIN first; now they just work. Renaming the
  badge doesn't break the app either.
- **Settings and the clock stay put.** Settings survive reboots and
  reflashes, and the clock survives reboots and switching off. It
  [drifts a lot](#ideas--not-done-yet), though, so set it now and then
  (`badgetool.py time`).
- **The battery voltage on the charging screen**, and a charging screen that
  lets the badge finish booting after 5 seconds instead of waiting for a
  button press forever.
- **Calmer buttons.** The button nearest USB steps one slot per press (the
  slots no longer start cycling on their own), a long press on the other
  button changes brightness, and the badge shows your slots straight away
  after booting and after an upload (a long press on the button nearest
  USB opens the menu).

### Always-on Bluetooth

On FOSSASIA's firmware the badge is only visible over Bluetooth while you
sit in the BT-PAIRING menu, and its "always on" setting never actually
switched advertising on. With the patched firmware and always-on enabled
(the default), the badge advertises from the moment it starts, every 60 to
125 ms, while it shows your slots, the clock or anything else. The phone
app or `badgetool.py --ble` can connect at any time without you touching the
badge.

- Switch it with `python badgetool.py ble on` / `ble off` (the badge
  reboots to apply it).
- With always-on off, the badge is only visible while you're in the
  BT-PAIRING menu. It goes quiet again once an upload finishes or you leave
  the menu. If something is still connected at that point, the connection
  stays open until it closes, and the badge doesn't advertise afterwards.
- While something is connected, the badge stops advertising: it takes one
  connection at a time. If a scan doesn't find it, close the other
  connection (the phone app, or the `badgetool.py` menu, which keeps its
  connection open until you quit it).
- It costs some battery even when nothing is connected; we haven't measured
  how much. Turn it off for long days on battery.
- The Bluetooth name shows in scans; the app finds the badge by its service
  ID, so any name works with the app.

## Supported badges

These badges are sold under many names, in different case and LED colours, so
the look doesn't tell you much. What matters is the chip inside. `badgetool.py
list` tells you which kind is plugged in by its USB name:

| Badge | USB name | What works |
|---|---|---|
| CH582, patched firmware | "FOSSASIA WAS HERE" | everything |
| CH582, factory firmware | "wch.cn" / "CH583" | text and images (USB and BLE) |
| LS32 (older, USB only) | "LS32 Custm HID" | text and images over USB |

All of them show up as USB device `0416:5020` and share the legacy "wang"
upload format, the same one the app uses. Only the patched firmware also
speaks the `ng` protocol, which handles settings, status, the clock and
streaming. If `list` says `unknown`, please open an issue with its output
(it shows the USB strings).

| CH582 badge (USB-C, 2 buttons) | LS32 badge (micro-USB) |
|---|---|
| ![CH582 board in its case](pictures/ch582-board-overview.jpg) | ![LS32 board](pictures/ls32-microusb-board.jpg) |
| ![CH582M chip close-up](pictures/ch582-chip-closeup.jpg) | ![LS32 chip close-up](pictures/ls32-microusb-chip.jpg) |

The CH582 board in these pictures is revision `B1144C_240525`. Look for the
`CH582M` marking on the chip.

## Requirements

- Python 3.11 or newer (for `tomllib`)
- `pip install hidapi bleak pillow`
  - `bleak` is only needed for Bluetooth
  - `pillow` is only needed for images
- Windows, Linux or macOS. Development and testing were done on Windows 11.
  On Linux, install [`linux/99-badgemagic.rules`](linux/99-badgemagic.rules)
  (instructions inside) to use the badge without `sudo`. The rule hasn't been
  tested on a Linux machine yet.

## Quick start

```sh
python badgetool.py                 # interactive menu: pick USB / BLE, then a badge
python badgetool.py list            # badges on USB
python badgetool.py status          # everything the badge reports
python badgetool.py text "Hello" "Second slot" --mode center
```

### Commands

| Command | What it does |
|---|---|
| `list` | badges on USB, or in range with `--ble` |
| `status` | mode, clock, brightness, Bluetooth settings, battery |
| `battery [-w SECONDS]` | voltage, raw ADC value and charging state, optionally refreshed |
| `time` | sets the badge clock to the PC time |
| `brightness 0-3` | 3 = brightest. 0 flickers slightly, by design |
| `ble on\|off` | always-on Bluetooth (badge reboots) |
| `name "NAME"` | Bluetooth name, max 20 characters (badge reboots) |
| `splash on\|off` | startup animation |
| `text MSG [MSG ...]` | one message per slot; options `--mode --speed --blink --border --font thin\|app --preview` |
| `upload config.toml` | a full Badge Magic config file (see below) |
| `image pic.png [--invert]` | static image in slot 1; dark pixels light up, `--invert` for light ones |
| `stream white\|off\|pic.png` | live picture without touching the slots |
| `reset` / `off` | reboot / power off |
| `flash normal` / `pb6` / `normal-fastble` / `pb6-fastble` / `FILE.bin` | flashes the patched firmware (badge in ISP mode, see [Which file](#which-file)) |

Scroll modes: `left right up down center fast drop curtain laser`. Speed: `0-7`.

### Choosing a badge

```sh
python badgetool.py status -i 1                      # second badge on USB
python badgetool.py status --ble                     # scan and pick
python badgetool.py status --ble AA:BB:CC:DD:EE:FF   # by Bluetooth address
python badgetool.py status --ble 11-22-33-44-55-66-77-88   # by chip UID (as wchisp prints it)
```

The options also work after the command (`badgetool.py text Hi --ble`).
You can do everything over BLE except `flash`. Over BLE, `status` and
`battery` show only the battery percentage and device info for now. A badge that is
connected stops advertising, so close other BLE sessions, such as the
interactive menu or the phone app, before you scan.

### Config file

Your slots live in `config.toml`, which comes with two example messages.
Edit it, then run `python badgetool.py upload config.toml` or use the menu.
The format is the same as the official `badgemagic` CLI's:

```toml
[[message]]
text = "HELLO"
mode = "center"

[[message]]
text = "scrolling text"
mode = "left"
speed = 6
border = false
blink = false
```

Up to 8 messages. A `brightness` line from the official CLI's files is
ignored; use `badgetool.py brightness` instead. A file saved with a UTF-8
BOM (e.g. by PowerShell) is read correctly.

## Example scripts (`ng/`)

Small standalone scripts from the development of the firmware, handy as
protocol examples. `badgetool.py` can do all of it too, so for normal use you
don't need them. **Read a script before running it:** several change and
save settings, and some reboot the badge. They only work with the patched
firmware.

| Script | What it does |
|---|---|
| `badge_ng.py` | minimal `ng` client over USB HID, plus `ble_find()` |
| `badge_display.py` | push PIL images to the badge as a live 44×11 display |
| `test_stream.py` | streaming test patterns, measures USB frame rate (~60 fps) |
| `battery.py`, `set_time.py`, `set_brightness.py` | single settings over USB |
| `ble_always_on.py`, `fix_alwayson.py`, `apply_cfg.py` | config + reboot (`apply_cfg.py` resets to defaults, including the name) |
| `ble_check.py` | connect over BLE and list services; optional address argument |
| `ble_fps.py`, `ble_ng_test.py` | BLE streaming speed (`ble_fps.py --invert` is the worst case with nearly every LED lit, `--csv` logs every frame) and `ng` commands over BLE (`ble_ng_test.py` leaves brightness at 3 until the next reboot) |

## The patched firmware

### Before you flash

- **There is no way back to the factory firmware.** It's read-protected, so
  it can't be backed up (only the settings memory can). The patched
  firmware does everything the factory one does and works with the Badge
  Magic app.
- **The first time into ISP mode can be fiddly.** On factory firmware the
  chip has to lose power completely. The battery is soldered on, so that
  means some soldering or upstream's capacitor trick (see [Flashing](#flashing)).
  After that, the patched firmware enters ISP mode with a 2 to 3 second
  button press.
- **A failed or wrong flash can be redone.** The ISP bootloader sits in its
  own protected area of the chip that flashing doesn't touch. If the badge
  shows garbage or nothing at all after a flash, enter ISP mode again and
  flash the right file.
- **Only CH582M badges with 44 columns.** Some badges look the same outside
  but have another chip or a 48 or 55 column matrix. If in doubt, open the
  case and read the chip marking. Upstream's
  [CH582.md](https://github.com/fossasia/badgemagic-firmware/blob/master/CH582.md)
  has photos.
- **The files here are for the 2-button USB-C version only,** the only one
  these patches were tested on. Upstream also supports 4 buttons and the older
  micro-USB boards (`KEY_COUNT=4`, `HARDWARE_REV1=1`). You can build those
  from source (see [Building](#building)), but they are untested with these
  patches.
- **`badgetool.py flash` runs `wchisp config reset` first,** like upstream's
  instructions do. Factory badges ship with read-out protection on and
  debugging off, and this writes WCH's default option bytes (no protection,
  debug enabled, reset pin on) so that the flash write and verify are
  allowed. It changes nothing else.

### Which file

Ready-to-flash builds are in [`firmware/`](firmware/), with checksums in
[`firmware/SHA256SUMS`](firmware/SHA256SUMS) (`sha256sum -c SHA256SUMS`).
They are also attached to the
[releases](https://github.com/Timon-sys/badgemagic-toolkit/releases).

Two choices make four files:

- **LED wiring:** `normal` for most boards, `pb6` for boards where LED line T
  is wired to PB6. Not sure? Flash `normal` first. If two columns stay dark
  and the second-to-last row flickers (there's a picture under
  [Fixes](#fixes)), flash `pb6`; nothing breaks either way.
- **Bluetooth speed:** the `fastble` builds ask for a 15 to 30 ms connection
  interval and use a bigger packet size (MTU 96), so live streaming over
  Bluetooth runs at about 20 fps instead of about 2. That costs more battery,
  but only while something is connected. Uploads, the phone app and
  everything else work the same in both.

| File | `flash` name | LED wiring | Bluetooth | Tested on a badge |
|---|---|---|---|---|
| `badgemagic-ch582-2key.bin` | `normal` | normal | standard | ran on a PB6 board (all but line T); upstream-wired board untested |
| `badgemagic-ch582-2key-pb6.bin` | `pb6` | PB6 | standard | yes, incl. a 150-frame Bluetooth stress test |
| `badgemagic-ch582-2key-fastble.bin` | `normal-fastble` | normal | fast | same code as `pb6-fastble` but the pin; upstream-wired board untested |
| `badgemagic-ch582-2key-pb6-fastble.bin` | `pb6-fastble` | PB6 | fast | yes, two badges, incl. the phone app (21 to 34 fps) |

The `normal` builds ran for weeks on our badges (an earlier version), and
everything worked except the LEDs on line T, because both our badges are
wired to PB6. What we couldn't test is a board actually wired the upstream
way, where `normal` should show the whole display. If you have one, please
[open an issue](https://github.com/Timon-sys/badgemagic-toolkit/issues) and
say whether it worked.

### Flashing

1. Get [wchisp](https://github.com/ch32-rs/wchisp/releases) and put it in
   `tools/` (`tools/wchisp-win-x64/` works too) or anywhere on your `PATH`.
2. One-time setup:
   - **Windows:** the first time a badge is in ISP mode, use
     [Zadig](https://zadig.akeo.ie/) to install WinUSB for `4348:55E0`.
   - **Linux:** install [`linux/99-badgemagic.rules`](linux/99-badgemagic.rules)
     (instructions inside), so neither the tool nor wchisp needs `sudo`.
3. Run `python badgetool.py flash normal` (or `flash pb6`). It waits up to
   5 minutes for a badge in ISP mode.
4. Enter ISP mode:
   - **Factory firmware (the hard part, only once):** the chip has to start
     up from no power at all while you hold the button **nearest the USB
     port**. Switching the badge off isn't enough, because the battery
     (which is soldered on) keeps the chip powered. Two ways:
     - desolder one battery lead, plug in USB with the button held, flash,
       and solder the lead back. The clean way.
     - upstream's quicker method: with USB connected and the button held,
       briefly short capacitor **C3** with tweezers or a wire. C3 sits on
       the power rail, so the short drops the voltage far enough to reset
       the chip: a "dirty power cycle". Upstream calls it less reliable
       than removing the battery, and shorting a neighbouring part by
       accident can damage the board, so it's not for beginners. On the
       revision in the picture below (`B1144C_240525`) C3 is next to the
       RESET button; on other revisions it sits elsewhere. Details in
       upstream's [CH582.md](https://github.com/fossasia/badgemagic-firmware/blob/master/CH582.md).

     The **RESET button doesn't work** for this: holding the button and
     pressing RESET only restarts the firmware (we tried it). It resets
     the chip without cutting power, and the boot pin is only checked on a
     real power-up.

     > ⚠️ **Never short the battery itself.** We got one badge into ISP
     > mode by shorting it for a split second while holding the button. It
     > worked, but a shorted LiPo cell can overheat, catch fire or burst.
     > Use one of the methods above.

     | C3 and RESET | KEY2 (nearest USB) and the soldered battery leads |
     |---|---|
     | ![C3, RESET and board revision](pictures/ch582-board-reset-c3-revision.jpg) | ![USB-C, KEY1, KEY2 and battery leads](pictures/ch582-board-usbc-buttons-battery.jpg) |

   - **Patched firmware already on it (every flash after the first):** with
     the badge connected over USB, hold the button nearest the USB port for
     2 to 3 seconds. No replugging, no tools. On the way it may jump to the
     menu; keep holding.

   ISP mode shows a single lit pixel near the middle and lasts about 10
   seconds, and `badgetool.py` starts flashing as soon as it sees the badge.
5. The tool flashes, verifies, waits for the badge to reboot and sets its
   clock.

wchisp only rewrites the program flash, so in our tests the slots and
settings survived a reflash. The first flash over factory firmware starts
with default settings, because this firmware stores them in a different
place than the factory one.

### Fixes

- **Refresh rate halved upstream:** commit `4e556ab` switched the LED scan
  from 2 to 4 phases per column (for 4 brightness levels), which doubled the
  steps per frame (44 to 88) but kept the 4 kHz timer, so a frame took 22 ms
  (about 45 Hz) and the scan was visible. The timer now runs at 8 kHz: 11 ms
  per frame, about 91 Hz.
- **Phone app uploads rejected:** the legacy BLE upload refused data as "not
  authed" unless the PIN feature was switched on (upstream issues #190 and
  #198). The check now only applies when the PIN is on.
- **Always-on Bluetooth did nothing:** advertising was only ever enabled by
  the BT-PAIRING menu, so the setting could only switch off something that
  was already off. It is now enabled at startup, and always-on is the
  default.
- **`ng` commands only over Bluetooth:** the USB HID and serial interfaces
  now feed the same command parser (framed as `'N' 'G' len payload`), and
  everything else still goes to the legacy upload, so the official CLI keeps
  working. This is what lets `badgetool.py` do everything over USB.
- **USB upload state never reset:** `legacy_usb_rx()` didn't reset its
  length counters after a transfer, so a following upload could be misread.
- **LEDs stuck on after switching off:** the LED timer kept running into
  power-off, leaving a column lit at full brightness. It is stopped first now.
- **Slots cycling on their own:** after the last slot, the button re-armed
  automatic cycling. Now it steps one slot per press and wraps around.
- **Badge stuck in the menu after an upload,** behind a "BLUETOOTH OFF"
  screen. It now shows the new slots straight away. It also boots into the
  slots instead of the menu.
- **Bluetooth "breathing" and dropped links:** the LED timer ticks every
  125 µs, and every Bluetooth connection interval is a multiple of 1.25 ms,
  so the radio events kept landing on the same point of the LED cycle and only
  drifted by the tiny crystal difference between badge and PC. Each time they
  drifted across the LED switching, packets got lost for seconds: streaming
  sped up and slowed down every 13 to 19 seconds (each badge has its own
  period), and with many LEDs lit the link dropped. The LED timer period now
  varies by up to 2 % per tick, which you can't see, so the interference is
  spread evenly. The fast-Bluetooth builds also ask for a 4-second supervision
  timeout instead of 1 second. With nearly every LED lit, streaming now runs
  at a steady 5 fps instead of 1.5 fps with dropped links.
- **Bluetooth animation after streaming:** with always-on off, stopping a
  stream always brought up the BT-PAIRING animation, as if every stream had
  started there. It now returns to your slots unless the badge really is in
  BT-PAIRING.
- **Full-width pictures blinked:** slot widths come in 8-column blocks, so
  a 44-column picture is stored as 48 columns. The still modes (fixed,
  up/down, drop, curtain, laser, animation) showed those 4 empty columns as
  a page of their own, and the display went dark every other page. A last
  page that is only padding is skipped now; one lit column on it keeps it.
- **Bluetooth stayed on after BT-PAIRING:** every disconnect switched
  advertising back on, so after one visit to the BT-PAIRING menu the badge
  stayed visible until the next reboot, even with always-on off. It now only
  advertises again if always-on is on or you're still in BT-PAIRING.
- **Startup animation:** off by default (`badgetool.py splash on` brings it
  back), so the badge is ready at once.
- **Bluetooth crash under load:** `ng_notify()` freed the notification
  buffer even after the Bluetooth stack had taken it over. That double free
  corrupted the Bluetooth heap: with notifications on and frames streamed
  fast, the badge's Bluetooth and buttons froze.
- **Slow Bluetooth** (`fastble` builds only): the badge allowed connection intervals up to 625 ms and
  never asked for less (its request went to the wrong connection), the MTU
  of 64 split every 89-byte stream frame into a 3-round-trip write, and the
  `ng` characteristic didn't allow writes without response. Now it asks for
  15 to 30 ms after connecting, uses MTU 96 and accepts write-without-response:
  live streaming went from about 2 to about 20 fps.
- **Dead columns / flickering row:** on some board revisions LED line T is
  wired to PB6 instead of the upstream pin. The symptom is two dark columns
  and the second-to-last row alternating between lit and dead. That's the
  `pb6` build (`LED_T_PB6=1`).

  ![All LEDs on with the wrong pin: a dark column on the right and a broken second-to-last row](pictures/badge-wrong-led-pin-before-fix.jpg)
- **Settings lost or overlapping the game highscore:** the config moved to
  `0x7C00`. It is now erased before it is written and goes through an aligned
  buffer, and its CRC is seeded so that an all-zero block no longer counts as
  valid.
- **USB HID replies dropped every other time:** the OUT handler no longer arms
  a zero-length IN, which knocked the data toggle out of step.
- **Stuck on the charging animation when plugged in:** the screen now leaves
  after 5 s or on a key press. The config is loaded before this screen, so a
  reboot while charging no longer saves zeros.
- **Bluetooth pairing menu:** leaving it no longer leaves the BLE animation
  fighting with the menu.

  ![The badge menu with its BT pairing animation](pictures/badge-menu-animation-bt-pairing.jpg)
- **Random bright pixel blips while redrawing:** the framebuffer is locked
  while it is cleared and redrawn, including in the games.
- **Bright blips when saving or during Bluetooth traffic:** a flash write
  stalls the LED refresh, so the lit column stayed on for milliseconds. The
  matrix now goes dark during flash writes instead, for under a tenth of a
  second when the brightness changes. The LED timer also gets a higher
  interrupt priority than the radio and USB, so it is never held up by them.
- **Streaming and clock fighting:** clock and stopwatch keep ticking while a
  stream is active but don't draw over it, and the badge returns to the
  previous screen when the stream stops.
- **Clock lost on every boot:** the RTC is only initialised when it holds no
  valid date, so the time survives reboots and a power-off with the button.

### Additions

- The charging screen shows the battery voltage (calibrated ADC).

  ![Charging screen with the battery voltage](pictures/badge-charging-screen-voltage.jpg)

- `ng` misc commands: set time (2), battery reply `BAT` (3), status reply
  `STA` (4).

### Building

You don't need to build anything to use the files in `firmware/`. To build
them yourself, get upstream at commit `b2137f0` and apply
[`badgemagic-custom-patches.diff`](badgemagic-custom-patches.diff). For the
`fastble` builds, apply [`badgemagic-fast-ble.diff`](badgemagic-fast-ble.diff)
on top:

```sh
git clone https://github.com/fossasia/badgemagic-firmware
cd badgemagic-firmware
git checkout b2137f0
git apply ../badgemagic-custom-patches.diff
git apply ../badgemagic-fast-ble.diff       # only for the fastble builds
```

The toolchain is `riscv-none-embed-gcc` 8.2 (MounRiver / xPack) plus `make`,
on Linux, macOS or Windows (we used Git Bash). If the compiler isn't on your
`PATH`, set `PREFIX` as upstream's README describes.

```sh
BUILD_DIR=usb-c-2key KEY_COUNT=2 make                  # normal build
BUILD_DIR=usb-c-2key-t6 KEY_COUNT=2 LED_T_PB6=1 make   # pb6 build
```

The result is `<BUILD_DIR>/badgemagic-ch582.bin`, and a clean checkout with
the patches builds byte-identical copies of the files in `firmware/`. Flash it
with `badgetool.py flash path/to/badgemagic-ch582.bin`.

## Protocol notes

| | USB HID (`0416:5020`) | BLE |
|---|---|---|
| Legacy upload | 64-byte reports | service `fee0`, characteristic `fee1`, 16-byte writes |
| `ng` commands | `'N' 'G' len16 payload` in 64-byte reports | service `f055`: write `f057`, notify `f056` |

`ng` commands: power (1), stream set (2), stream bitmap (3), BLE settings (4),
save (6), misc (8: splash, brightness, time, battery, status).

The Badge Magic app finds badges by the advertised service `0xFEE0`, so
renaming a badge keeps it compatible with the app.

## Ideas / not done yet

- **USB serial (CDC):** Windows rejects the port with error 31 because the
  firmware ignores the line-coding requests (`SET_LINE_CODING`,
  `GET_LINE_CODING`, `SET_CONTROL_LINE_STATE`). The CDC OUT handler also
  still has the zero-length-IN bug that was fixed for HID. `--serial` is a
  stub until that is fixed.
- **Status and battery over BLE:** the replies currently go out over USB HID
  only. Sending them as `f056` notifications would give BLE the full
  `status` (voltage, clock, settings) instead of just the battery percentage.
- **Smoother BLE streaming:** frames arrive on the connection-interval grid
  (Windows picks 30 ms), so streams at 15 or 20 fps jitter by a slot now and
  then. A 7.5 to 15 ms interval would make it smoother, at more battery cost
  while connected.
- **Battery cost of always-on Bluetooth:** not measured yet.
- **Remote mode switching:** a command to switch between clock, stopwatch,
  slots (or one specific slot) and menu from the PC, over USB and BLE. Today
  only the buttons can do that.
- **The clock drifts a lot:** the badge has no 32 kHz crystal, so the clock
  runs on the chip's internal RC oscillator. Measured on one badge: it drifts
  by about 10 % (1 s every 10 s), sometimes slow, sometimes fast. The
  calibration against the main crystal (`Calibration_LSI`) apparently doesn't
  hold. Set the clock with `badgetool.py time` when you need it; fixing it
  would mean recalibrating periodically or correcting the RTC in software.
- **Upstream pull requests:** several fixes (config storage, the HID reply
  bug, `LED_T_PB6`, the blips, the charging screen) would be useful for
  FOSSASIA too.

## Credits and licences

- Made by me together with
  [Claude](https://claude.com/claude-code) (Anthropic's AI assistant): the
  firmware debugging, the patches, `badgetool.py` and this README were worked
  out in pair-programming sessions, with every change tested on real badges.
- This project is licensed under [Apache-2.0](LICENSE), the same as the
  firmware it is based on.
- Firmware: [FOSSASIA badgemagic-firmware](https://github.com/fossasia/badgemagic-firmware)
  (Apache-2.0). The patches and the builds in `firmware/` follow the same licence.
- Thin font: `u8g2_font_lucasfont_alternate_tf` from
  [u8g2](https://github.com/olikraus/u8g2) (Lucasfont Alternate © Patrick
  Lauke 2012, made with [FontStruct](https://fontstruct.com/fontstructors/145/redux)).
  This is the same font the [badgemagic-rs](https://github.com/fossasia/badgemagic-rs)
  CLI uses. Its licence is believed to be
  [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/), like the author's
  other FontStructions, but the font's own page couldn't be found. If you know
  better, please open an issue.
- App font table: [FOSSASIA badgemagic-app](https://github.com/fossasia/badgemagic-app) (Apache-2.0).
- Flashing: [wchisp](https://github.com/ch32-rs/wchisp).

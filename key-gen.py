
#!/usr/bin/env python3
"""Type ASCII text through a virtual keyboard visible to Wayland compositors."""

import argparse
import fcntl
import os
import struct
import sys
import time


EV_SYN = 0
EV_KEY = 1
SYN_REPORT = 0
KEY_LEFTSHIFT = 42


def ioctl_code(direction, kind, number, size=0):
    return (direction << 30) | (size << 16) | (ord(kind) << 8) | number


def ioctl_write(kind, number):
    return ioctl_code(1, kind, number, 4)


UI_DEV_CREATE = ioctl_code(0, "U", 1)
UI_DEV_DESTROY = ioctl_code(0, "U", 2)
UI_SET_EVBIT = ioctl_write("U", 100)
UI_SET_KEYBIT = ioctl_write("U", 101)


# Linux evdev key codes for a US-layout keyboard.
LETTER_CODES = (
    30, 48, 46, 32, 18, 33, 34, 35, 23, 36, 37, 38, 50,
    49, 24, 25, 16, 19, 31, 20, 22, 47, 17, 45, 21, 44,
)
KEYS = {
    **{character: (code, False) for character, code in zip(
        "abcdefghijklmnopqrstuvwxyz", LETTER_CODES
    )},
    **{character.upper(): (code, True) for character, code in zip(
        "abcdefghijklmnopqrstuvwxyz", LETTER_CODES
    )},
    **{character: (code, False) for character, code in zip(
        "1234567890", (2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
    )},
    " ": (57, False),
    "\n": (28, False),
    "\t": (15, False),
    "\b": (14, False),
    "`": (41, False), "~": (41, True),
    "-": (12, False), "_": (12, True),
    "=": (13, False), "+": (13, True),
    "[": (26, False), "{": (26, True),
    "]": (27, False), "}": (27, True),
    "\\": (43, False), "|": (43, True),
    ";": (39, False), ":": (39, True),
    "'": (40, False), '"': (40, True),
    ",": (51, False), "<": (51, True),
    ".": (52, False), ">": (52, True),
    "/": (53, False), "?": (53, True),
    **{character: (code, True) for character, code in zip(
        "!@#$%^&*()", (2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
    )},
}


def validate_text(text):
    for character in text:
        if character not in KEYS:
            raise ValueError(
                f"Unsupported character: {character!r} (use ASCII keyboard text)"
            )


def make_keyboard():
    fd = os.open("/dev/uinput", os.O_WRONLY | os.O_CLOEXEC)
    created = False
    try:
        fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
        used_codes = {KEY_LEFTSHIFT}
        for code, shifted in KEYS.values():
            used_codes.add(code)
            if shifted:
                used_codes.add(KEY_LEFTSHIFT)
        for code in used_codes:
            fcntl.ioctl(fd, UI_SET_KEYBIT, code)

        descriptor = struct.pack(
            "@80sHHHHI", b"ubuntu-control synthetic keyboard", 0x03, 0x1, 0x1, 1, 0
        ) + struct.pack("@256i", *([0] * 256))
        os.write(fd, descriptor)
        fcntl.ioctl(fd, UI_DEV_CREATE)
        created = True
        time.sleep(0.1)
        return fd
    except BaseException:
        try:
            if created:
                fcntl.ioctl(fd, UI_DEV_DESTROY)
        finally:
            os.close(fd)
        raise


def emit(fd, event_type, code, value):
    sec, usec = divmod(time.time_ns() // 1000, 1_000_000)
    event = struct.pack("@llHHi", sec, usec, event_type, code, value)
    os.write(fd, event)
    os.write(fd, struct.pack("@llHHi", sec, usec, EV_SYN, SYN_REPORT, 0))


def type_text(fd, text, duration, interval):
    for character in text:
        code, shifted = KEYS[character]
        if shifted:
            emit(fd, EV_KEY, KEY_LEFTSHIFT, 1)
        emit(fd, EV_KEY, code, 1)
        time.sleep(duration)
        emit(fd, EV_KEY, code, 0)
        if shifted:
            emit(fd, EV_KEY, KEY_LEFTSHIFT, 0)
        if interval:
            time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", help="ASCII text to type")
    parser.add_argument(
        "--duration", type=float, default=0.01,
        help="seconds to hold each key down (default: 0.01)",
    )
    parser.add_argument(
        "--interval", type=float, default=0.01,
        help="seconds between characters (default: 0.01)",
    )
    args = parser.parse_args()
    if args.duration < 0 or args.interval < 0:
        parser.error("--duration and --interval must be non-negative")

    try:
        validate_text(args.text)
    except ValueError as exc:
        parser.error(str(exc))

    fd = None
    try:
        fd = make_keyboard()
        type_text(fd, args.text, args.duration, args.interval)
    except PermissionError as exc:
        print(
            f"Cannot open /dev/uinput: {exc}. Grant this user access to /dev/uinput "
            "or run the script with appropriate privileges.",
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError) as exc:
        print(f"Could not generate key presses: {exc}", file=sys.stderr)
        return 1
    finally:
        if fd is not None:
            try:
                fcntl.ioctl(fd, UI_DEV_DESTROY)
            finally:
                os.close(fd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

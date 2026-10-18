#!/usr/bin/env python3
"""Move the pointer using a string of u/d/l/r directions."""

import argparse
import fcntl
import os
import struct
import sys
import time


EV_SYN = 0
EV_KEY = 1
EV_REL = 2
SYN_REPORT = 0
BTN_LEFT = 0x110
BTN_RIGHT = 0x111
BTN_MIDDLE = 0x112
REL_X = 0
REL_Y = 1
STEP_SIZE = 20


def ioctl_code(direction, kind, number, size=0):
    return (direction << 30) | (size << 16) | (ord(kind) << 8) | number


def ioctl_write(kind, number):
    return ioctl_code(1, kind, number, 4)


UI_DEV_CREATE = ioctl_code(0, "U", 1)
UI_DEV_DESTROY = ioctl_code(0, "U", 2)
UI_SET_EVBIT = ioctl_write("U", 100)
UI_SET_KEYBIT = ioctl_write("U", 101)
UI_SET_RELBIT = ioctl_write("U", 102)

MOVEMENTS = {
    "u": (REL_Y, -STEP_SIZE),
    "d": (REL_Y, STEP_SIZE),
    "l": (REL_X, -STEP_SIZE),
    "r": (REL_X, STEP_SIZE),
}


def validate_directions(directions):
    invalid = next((character for character in directions if character not in MOVEMENTS), None)
    if invalid is not None:
        raise ValueError(f"Unsupported direction: {invalid!r} (use only u, d, l, r)")


def make_mouse():
    fd = os.open("/dev/uinput", os.O_WRONLY | os.O_CLOEXEC)
    created = False
    try:
        # udev/libinput only classify a device as a mouse if it has buttons too.
        fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
        for button in (BTN_LEFT, BTN_RIGHT, BTN_MIDDLE):
            fcntl.ioctl(fd, UI_SET_KEYBIT, button)
        fcntl.ioctl(fd, UI_SET_EVBIT, EV_REL)
        fcntl.ioctl(fd, UI_SET_RELBIT, REL_X)
        fcntl.ioctl(fd, UI_SET_RELBIT, REL_Y)

        descriptor = struct.pack(
            "@80sHHHHI", b"ubuntu-control synthetic mouse", 0x03, 0x1, 0x2, 1, 0
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


def move_pointer(fd, directions, interval):
    for direction in directions:
        code, distance = MOVEMENTS[direction]
        emit(fd, EV_REL, code, distance)
        if interval:
            time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directions", help="movement sequence containing only u, d, l, r")
    parser.add_argument(
        "--interval", type=float, default=0.01,
        help="seconds between movements (default: 0.01)",
    )
    args = parser.parse_args()
    if args.interval < 0:
        parser.error("--interval must be non-negative")

    try:
        validate_directions(args.directions)
    except ValueError as exc:
        parser.error(str(exc))

    fd = None
    try:
        fd = make_mouse()
        move_pointer(fd, args.directions, args.interval)
        time.sleep(0.1)
    except PermissionError as exc:
        print(
            f"Cannot open /dev/uinput: {exc}. Grant this user access to /dev/uinput "
            "or run the script with appropriate privileges.",
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        print(f"Could not generate mouse movements: {exc}", file=sys.stderr)
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

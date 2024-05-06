"""macOS-only helper to run as a menu-bar 'accessory' app (no Dock icon).

The packaged .app sets LSUIElement in Info.plist, but when running from source
we flip the activation policy at runtime via the Objective-C runtime (ctypes,
no pyobjc dependency). Best-effort: any failure is silently ignored.
"""
from __future__ import annotations

import sys


def hide_dock_icon() -> None:
    if sys.platform != "darwin":
        return
    try:
        import ctypes
        import ctypes.util

        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]

        send = objc.objc_msgSend
        send.restype = ctypes.c_void_p
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

        ns_app_cls = objc.objc_getClass(b"NSApplication")
        shared = send(ns_app_cls, objc.sel_registerName(b"sharedApplication"))

        # setActivationPolicy: takes a long (NSApplicationActivationPolicyAccessory = 1)
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
        send(shared, objc.sel_registerName(b"setActivationPolicy:"), 1)
    except Exception:  # noqa: BLE001 - purely cosmetic, never fatal
        pass

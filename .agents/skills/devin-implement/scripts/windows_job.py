"""Contain a local worker's ordinary child processes without changing its permissions.

The supervisor owns the job; a Python bootstrap joins it before launching Devin.
This avoids the launch/assignment race and kills descendants if the supervisor dies.
Jobs manage lifetime, not filesystem/network security or work in external services.
"""

import ctypes
from ctypes import wintypes as wt
import os
import subprocess
import sys
import threading
import time
import uuid


class BasicLimits(ctypes.Structure):
    """Match JOBOBJECT_BASIC_LIMIT_INFORMATION using pointer-sized native fields."""

    _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                ("flags", wt.DWORD), ("min_working_set", ctypes.c_size_t),
                ("max_working_set", ctypes.c_size_t), ("active_limit", wt.DWORD),
                ("affinity", ctypes.c_size_t), ("priority", wt.DWORD),
                ("scheduling", wt.DWORD)]


class ExtendedLimits(ctypes.Structure):
    """Match the extended limits structure; only KILL_ON_JOB_CLOSE is enabled."""

    _fields_ = [("basic", BasicLimits), ("io", ctypes.c_uint64 * 6),
                ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]


class Accounting(ctypes.Structure):
    """Expose ActiveProcesses so cleanup is verified before releasing ownership."""

    _fields_ = [("times", ctypes.c_int64 * 4), ("faults", wt.DWORD),
                ("total", wt.DWORD), ("active", wt.DWORD), ("terminated", wt.DWORD)]


def kernel():
    """Bind the narrow Win32 surface with explicit signatures on 32/64-bit Python."""
    if os.name != "nt":
        raise RuntimeError("This launcher requires native Windows; no uncontained fallback.")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateJobObjectW": ([ctypes.c_void_p, wt.LPCWSTR], wt.HANDLE),
        "OpenJobObjectW": ([wt.DWORD, wt.BOOL, wt.LPCWSTR], wt.HANDLE),
        "SetInformationJobObject": ([wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD], wt.BOOL),
        "QueryInformationJobObject": ([wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD, ctypes.c_void_p], wt.BOOL),
        "AssignProcessToJobObject": ([wt.HANDLE, wt.HANDLE], wt.BOOL),
        "GetCurrentProcess": ([], wt.HANDLE),
        "TerminateJobObject": ([wt.HANDLE, wt.UINT], wt.BOOL),
        "CloseHandle": ([wt.HANDLE], wt.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        getattr(api, name).argtypes = arguments
        getattr(api, name).restype = result
    return api


def checked(value):
    """Fail before proceeding when a native ownership operation is unsuccessful."""
    if not value:
        raise ctypes.WinError(ctypes.get_last_error())
    return value


class Job:
    """Own one worker process tree; never attach a persistent editor or other agent."""

    def __init__(self):
        """Create a uniquely named job whose final handle closes all member processes."""
        self.api = kernel()
        self.name = "Local\\devin-implement-" + uuid.uuid4().hex
        self.handle = checked(self.api.CreateJobObjectW(None, self.name))
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
        try:
            checked(self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
        except BaseException:
            self.api.CloseHandle(self.handle)
            raise

    def active(self):
        """Return remaining member processes, including the bootstrap and descendants."""
        info = Accounting()
        checked(self.api.QueryInformationJobObject(self.handle, 1, ctypes.byref(info), ctypes.sizeof(info), None))
        return info.active

    def stop(self):
        """Terminate only this job and confirm zero writers, or leave cleanup unresolved."""
        checked(self.api.TerminateJobObject(self.handle, 125))
        deadline = time.monotonic() + 10
        while self.active():
            if time.monotonic() >= deadline:
                raise RuntimeError("Worker process cleanup did not complete within 10 seconds.")
            time.sleep(0.05)

    def close(self):
        """Close the supervisor's handle; Windows also cleans up on supervisor death."""
        if self.handle:
            checked(self.api.CloseHandle(self.handle))
            self.handle = None


def console_output(command, cwd):
    """Mirror the headless CLI's live stdout/stderr to its console and retained log handles."""
    with open("CONOUT$", "w", encoding="utf-8", buffering=1) as console:
        display_lock = threading.Lock()
        with subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            def copy(stream, log):
                """Drain one stream continuously, preserving raw logs and displaying decoded text."""
                import codecs
                decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
                while chunk := stream.read1(4096):
                    log.write(chunk)
                    log.flush()
                    with display_lock:
                        console.write(decoder.decode(chunk))
                        console.flush()
                with display_lock:
                    console.write(decoder.decode(b"", final=True))

            errors = threading.Thread(target=copy, args=(process.stderr, sys.stderr.buffer))
            errors.start()
            copy(process.stdout, sys.stdout.buffer)
            errors.join()
            return process.wait()


def bootstrap(job_name, cwd, command):
    """Join the supervisor job before any Devin executable or child can start."""
    api = kernel()
    handle = checked(api.OpenJobObjectW(0x0001, False, job_name))  # ASSIGN_PROCESS
    try:
        checked(api.AssignProcessToJobObject(handle, api.GetCurrentProcess()))
    finally:
        checked(api.CloseHandle(handle))
    if os.environ.get("DEVIN_IMPLEMENT_CONSOLE") == "1":
        return console_output(command, cwd)
    return subprocess.call(command, cwd=cwd, stdin=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW)


if __name__ == "__main__":
    sys.exit(bootstrap(sys.argv[1], sys.argv[2], sys.argv[3:]))

"""Windows-only native handle traversal.

Opens a directory exactly once as a native NT handle, enumerates its
children through that handle, and opens every child *relative to the
parent's handle* (`NtCreateFile` with `RootDirectory` set) instead of by
re-resolving a composed path string. Because a child is never reopened by
name after the initial lookup, a rename or junction/symlink swap performed
after the handle exists cannot redirect it: the handle keeps pointing at the
original file-system object. Every entry is opened with
`FILE_OPEN_REPARSE_POINT` so reparse points (symlinks, junctions, mount
points) are surfaced to us instead of being transparently followed, and any
reparse point discovered during enumeration causes the whole enumeration to
be rejected.

This module is Windows-only. Importing it on any other platform raises
immediately; callers are responsible for guarding usage by platform.
"""

from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass

from .input_policy import InputViolation, safe_text

if sys.platform != "win32":
    raise RuntimeError("simaticml_decoder.windows_handles is only available on Windows")

# --- NTSTATUS / flag constants -------------------------------------------------

# ACCESS_MASK / DesiredAccess bits.
SYNCHRONIZE = 0x00100000
FILE_READ_DATA = 0x00000001
FILE_LIST_DIRECTORY = 0x00000001
FILE_READ_ATTRIBUTES = 0x00000080

# CreateOptions bits.
FILE_DIRECTORY_FILE = 0x00000001
FILE_NON_DIRECTORY_FILE = 0x00000040
FILE_SYNCHRONOUS_IO_NONALERT = 0x00000020
FILE_OPEN_REPARSE_POINT = 0x00200000

# ShareAccess bits.
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004

# CreateDisposition.
FILE_OPEN = 0x00000001

# OBJECT_ATTRIBUTES.Attributes.
OBJ_CASE_INSENSITIVE = 0x00000040

# File attribute bits (as reported by FILE_ID_BOTH_DIR_INFORMATION).
FILE_ATTRIBUTE_DIRECTORY = 0x00000010
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400

# FILE_INFORMATION_CLASS value for NtQueryDirectoryFile. This is the only
# information class this module uses.
FILE_ID_BOTH_DIRECTORY_INFORMATION = 37


def _nt_status(unsigned_value: int) -> int:
    """Reinterpret an unsigned 32-bit NTSTATUS literal as the signed value
    ctypes produces from a `c_long`-typed return."""
    return ctypes.c_long(unsigned_value).value


STATUS_SUCCESS = 0
STATUS_NO_MORE_FILES = _nt_status(0x80000006)


# --- ctypes structures (exact Windows SDK / winternl.h layouts) ---------------


class UNICODE_STRING(ctypes.Structure):
    _fields_ = (
        ("Length", ctypes.c_ushort),
        ("MaximumLength", ctypes.c_ushort),
        ("Buffer", ctypes.c_wchar_p),
    )


class OBJECT_ATTRIBUTES(ctypes.Structure):
    _fields_ = (
        ("Length", ctypes.c_ulong),
        ("RootDirectory", ctypes.c_void_p),
        ("ObjectName", ctypes.POINTER(UNICODE_STRING)),
        ("Attributes", ctypes.c_ulong),
        ("SecurityDescriptor", ctypes.c_void_p),
        ("SecurityQualityOfService", ctypes.c_void_p),
    )


class _IoStatusUnion(ctypes.Union):
    _fields_ = (
        ("Status", ctypes.c_ulong),
        ("Pointer", ctypes.c_void_p),
    )


class IO_STATUS_BLOCK(ctypes.Structure):
    _anonymous_ = ("_status",)
    _fields_ = (
        ("_status", _IoStatusUnion),
        ("Information", ctypes.c_size_t),
    )


class FILETIME(ctypes.Structure):
    _fields_ = (
        ("dwLowDateTime", ctypes.c_ulong),
        ("dwHighDateTime", ctypes.c_ulong),
    )


class BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
    """Exact `kernel32.h` layout. Only `dwFileAttributes` (the first field)
    is used here, but `GetFileInformationByHandle` writes the whole
    structure, so every field must be declared with its real width."""

    _fields_ = (
        ("dwFileAttributes", ctypes.c_ulong),
        ("ftCreationTime", FILETIME),
        ("ftLastAccessTime", FILETIME),
        ("ftLastWriteTime", FILETIME),
        ("dwVolumeSerialNumber", ctypes.c_ulong),
        ("nFileSizeHigh", ctypes.c_ulong),
        ("nFileSizeLow", ctypes.c_ulong),
        ("nNumberOfLinks", ctypes.c_ulong),
        ("nFileIndexHigh", ctypes.c_ulong),
        ("nFileIndexLow", ctypes.c_ulong),
    )


class FILE_ID_BOTH_DIR_INFORMATION(ctypes.Structure):
    """Fixed-size prefix of `FILE_ID_BOTH_DIR_INFORMATION`.

    The real structure ends with a variable-length trailing `WCHAR
    FileName[1]` array, which cannot be expressed as a fixed ctypes field.
    Callers read `FileNameLength` bytes starting at
    `ctypes.sizeof(FILE_ID_BOTH_DIR_INFORMATION)` past this structure's
    address instead.
    """

    _fields_ = (
        ("NextEntryOffset", ctypes.c_ulong),
        ("FileIndex", ctypes.c_ulong),
        ("CreationTime", ctypes.c_longlong),
        ("LastAccessTime", ctypes.c_longlong),
        ("LastWriteTime", ctypes.c_longlong),
        ("ChangeTime", ctypes.c_longlong),
        ("EndOfFile", ctypes.c_longlong),
        ("AllocationSize", ctypes.c_longlong),
        ("FileAttributes", ctypes.c_ulong),
        ("FileNameLength", ctypes.c_ulong),
        ("EaSize", ctypes.c_ulong),
        ("ShortNameLength", ctypes.c_byte),
        ("ShortName", ctypes.c_wchar * 12),
        ("FileId", ctypes.c_longlong),
    )


# --- Native API bindings -------------------------------------------------------

_ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_NtCreateFile = _ntdll.NtCreateFile
_NtCreateFile.restype = ctypes.c_long
_NtCreateFile.argtypes = (
    ctypes.POINTER(ctypes.c_void_p),  # PHANDLE FileHandle
    ctypes.c_ulong,  # ACCESS_MASK DesiredAccess
    ctypes.POINTER(OBJECT_ATTRIBUTES),  # POBJECT_ATTRIBUTES ObjectAttributes
    ctypes.POINTER(IO_STATUS_BLOCK),  # PIO_STATUS_BLOCK IoStatusBlock
    ctypes.POINTER(ctypes.c_longlong),  # PLARGE_INTEGER AllocationSize
    ctypes.c_ulong,  # ULONG FileAttributes
    ctypes.c_ulong,  # ULONG ShareAccess
    ctypes.c_ulong,  # ULONG CreateDisposition
    ctypes.c_ulong,  # ULONG CreateOptions
    ctypes.c_void_p,  # PVOID EaBuffer
    ctypes.c_ulong,  # ULONG EaLength
)

_NtQueryDirectoryFile = _ntdll.NtQueryDirectoryFile
_NtQueryDirectoryFile.restype = ctypes.c_long
_NtQueryDirectoryFile.argtypes = (
    ctypes.c_void_p,  # HANDLE FileHandle
    ctypes.c_void_p,  # HANDLE Event
    ctypes.c_void_p,  # PIO_APC_ROUTINE ApcRoutine
    ctypes.c_void_p,  # PVOID ApcContext
    ctypes.POINTER(IO_STATUS_BLOCK),  # PIO_STATUS_BLOCK IoStatusBlock
    ctypes.c_void_p,  # PVOID FileInformation
    ctypes.c_ulong,  # ULONG Length
    ctypes.c_ulong,  # FILE_INFORMATION_CLASS FileInformationClass
    ctypes.c_byte,  # BOOLEAN ReturnSingleEntry
    ctypes.POINTER(UNICODE_STRING),  # PUNICODE_STRING FileName
    ctypes.c_byte,  # BOOLEAN RestartScan
)

_CloseHandle = _kernel32.CloseHandle
_CloseHandle.restype = ctypes.c_int
_CloseHandle.argtypes = (ctypes.c_void_p,)

_ReadFile = _kernel32.ReadFile
_ReadFile.restype = ctypes.c_int
_ReadFile.argtypes = (
    ctypes.c_void_p,  # HANDLE hFile
    ctypes.c_void_p,  # LPVOID lpBuffer
    ctypes.c_ulong,  # DWORD nNumberOfBytesToRead
    ctypes.POINTER(ctypes.c_ulong),  # LPDWORD lpNumberOfBytesRead
    ctypes.c_void_p,  # LPOVERLAPPED lpOverlapped
)

_GetFileInformationByHandle = _kernel32.GetFileInformationByHandle
_GetFileInformationByHandle.restype = ctypes.c_int
_GetFileInformationByHandle.argtypes = (
    ctypes.c_void_p,  # HANDLE hFile
    ctypes.POINTER(BY_HANDLE_FILE_INFORMATION),  # LPBY_HANDLE_FILE_INFORMATION lpFileInformation
)


# --- Public value types ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class NativeEntry:
    """One directory entry discovered through a native handle.

    ``is_reparse_point``/``size`` are populated from the same
    `FILE_ID_BOTH_DIR_INFORMATION` record `entries()` already reads for every
    entry -- no extra native call. ``size`` mirrors `EndOfFile` and is only
    meaningful for non-directory entries.
    """

    name: str
    is_directory: bool
    is_reparse_point: bool = False
    size: int = 0


# --- Helpers ----------------------------------------------------------------


def _to_nt_path(path: object) -> str:
    """Turn a filesystem path into an NT native-namespace path.

    Uses lexical, CWD-relative normalization only (`os.path.abspath`) and
    never follows symlinks: the root is opened exactly once by this path,
    so resolving it through the filesystem here would reintroduce the same
    TOCTOU window this module exists to close.
    """
    absolute = os.path.abspath(str(path))
    if absolute.startswith("\\\\"):
        return f"\\??\\UNC\\{absolute[2:]}"
    return f"\\??\\{absolute}"


def _validate_child_name(name: str) -> None:
    if name in (".", "..") or "\\" in name or "/" in name:
        raise InputViolation("invalid_entry_name", "entry name is not accepted")


def _make_unicode_string(text: str) -> tuple[UNICODE_STRING, ctypes.Array]:
    buffer = ctypes.create_unicode_buffer(text)
    length = len(text) * ctypes.sizeof(ctypes.c_wchar)
    unicode_string = UNICODE_STRING(length, length, ctypes.cast(buffer, ctypes.c_wchar_p))
    return unicode_string, buffer


def _raise_native_failure(operation: str, status: int) -> None:
    raise InputViolation(
        "unreadable_input",
        safe_text(f"native {operation} failed (status 0x{status & 0xFFFFFFFF:08X})"),
    )


def _nt_create_file(
    root_handle: int | None, name: str, desired_access: int, create_options: int
) -> int:
    unicode_string, _buffer = _make_unicode_string(name)
    attributes = OBJECT_ATTRIBUTES(
        ctypes.sizeof(OBJECT_ATTRIBUTES),
        root_handle,
        ctypes.pointer(unicode_string),
        OBJ_CASE_INSENSITIVE,
        None,
        None,
    )
    io_status = IO_STATUS_BLOCK()
    handle = ctypes.c_void_p()
    status = _NtCreateFile(
        ctypes.byref(handle),
        desired_access,
        ctypes.byref(attributes),
        ctypes.byref(io_status),
        None,
        0,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        FILE_OPEN,
        create_options,
        None,
        0,
    )
    if status != STATUS_SUCCESS:
        _raise_native_failure("open", status)
    return handle.value  # type: ignore[return-value]


def _close_handle(handle: int | None) -> None:
    if handle:
        _CloseHandle(ctypes.c_void_p(handle))


def _reject_if_reparse_point(handle: int) -> None:
    """Re-check a freshly-opened handle's own attributes for
    `FILE_ATTRIBUTE_REPARSE_POINT`.

    `entries()` already rejects any reparse point *seen during
    enumeration*, but there is a narrow window between that `entries()` call
    and a later `open_child(name, ...)` call in which the target could be
    swapped for a reparse point. Every open already passes
    `FILE_OPEN_REPARSE_POINT`, so the OS never transparently follows a
    reparse point to its target even in that race -- the security invariant
    holds regardless -- but without this check, a race like that would
    surface as an assorted native I/O failure on a later read/enumerate
    against the reparse point itself, instead of a clean, deterministic
    rejection here, at the moment the reparse point was actually opened.
    """
    info = BY_HANDLE_FILE_INFORMATION()
    ok = _GetFileInformationByHandle(ctypes.c_void_p(handle), ctypes.byref(info))
    if not ok:
        error = ctypes.get_last_error()
        raise InputViolation(
            "unreadable_input", safe_text(f"native attribute query failed (code {error})")
        )
    if info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT:
        raise InputViolation("symlink_not_allowed", "symbolic links are not accepted")


# --- Public handle types -----------------------------------------------------


class NativeHandle:
    """A native file handle opened relative to its parent directory's handle."""

    def __init__(self, handle: int) -> None:
        self._handle: int | None = handle

    def __enter__(self) -> NativeHandle:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()

    def close(self) -> None:
        _close_handle(self._handle)
        self._handle = None

    def read_limited(self, limit: int) -> bytes:
        """Read at most `limit + 1` bytes so callers can detect oversized
        input without reading the full (potentially huge) file."""
        if self._handle is None:
            raise InputViolation("unreadable_input", "native handle is already closed")
        to_read = limit + 1
        buffer = ctypes.create_string_buffer(to_read)
        bytes_read = ctypes.c_ulong(0)
        ok = _ReadFile(self._handle, buffer, to_read, ctypes.byref(bytes_read), None)
        if not ok:
            error = ctypes.get_last_error()
            raise InputViolation(
                "unreadable_input", safe_text(f"native read failed (code {error})")
            )
        return buffer.raw[: bytes_read.value]


class NativeDirectory:
    """A native directory handle anchoring all descendant opens.

    Children are opened via `open_child` relative to this handle
    (`NtCreateFile` with `RootDirectory` set), never by composing and
    re-resolving a path string.
    """

    def __init__(self, handle: int) -> None:
        self._handle: int | None = handle

    def __enter__(self) -> NativeDirectory:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()

    def close(self) -> None:
        _close_handle(self._handle)
        self._handle = None

    @classmethod
    def open_root(cls, path: object) -> NativeDirectory:
        """Open the root directory exactly once, by its NT native path."""
        nt_path = _to_nt_path(path)
        handle = _nt_create_file(
            None,
            nt_path,
            SYNCHRONIZE | FILE_READ_ATTRIBUTES | FILE_LIST_DIRECTORY,
            FILE_DIRECTORY_FILE | FILE_OPEN_REPARSE_POINT | FILE_SYNCHRONOUS_IO_NONALERT,
        )
        return cls(handle)

    def open_child(self, name: str, directory: bool) -> NativeDirectory | NativeHandle:
        """Open a child by name, relative to this directory's own handle.

        Rejects `.`/`..` and any name containing a path separator before
        the name ever reaches `NtCreateFile`. After the open succeeds, the
        freshly-opened handle is re-checked for `FILE_ATTRIBUTE_REPARSE_POINT`
        (see `_reject_if_reparse_point`) to close the narrow enumerate-then-
        open race with a clean `InputViolation("symlink_not_allowed", ...)`
        instead of an assorted native failure surfacing later.
        """
        _validate_child_name(name)
        if self._handle is None:
            raise InputViolation("unreadable_input", "native handle is already closed")
        if directory:
            handle = _nt_create_file(
                self._handle,
                name,
                SYNCHRONIZE | FILE_READ_ATTRIBUTES | FILE_LIST_DIRECTORY,
                FILE_DIRECTORY_FILE | FILE_OPEN_REPARSE_POINT | FILE_SYNCHRONOUS_IO_NONALERT,
            )
            try:
                _reject_if_reparse_point(handle)
                return NativeDirectory(handle)
            except Exception:
                _close_handle(handle)
                raise
        handle = _nt_create_file(
            self._handle,
            name,
            SYNCHRONIZE | FILE_READ_ATTRIBUTES | FILE_READ_DATA,
            FILE_NON_DIRECTORY_FILE | FILE_OPEN_REPARSE_POINT | FILE_SYNCHRONOUS_IO_NONALERT,
        )
        try:
            _reject_if_reparse_point(handle)
            return NativeHandle(handle)
        except Exception:
            _close_handle(handle)
            raise

    def entries(self, *, reject_reparse_points: bool = True) -> tuple[NativeEntry, ...]:
        """Enumerate immediate children by this directory's own handle.

        By default (``reject_reparse_points=True`` -- the existing hard-fail
        directory-mode contract, unchanged), any child carrying
        `FILE_ATTRIBUTE_REPARSE_POINT` (symlink, junction, or mount point)
        aborts the whole enumeration rather than being silently skipped.

        ``reject_reparse_points=False`` (used only by project-mode's
        soft-diagnostic walk) keeps the identical native enumeration but
        stops treating a reparse point as fatal: it is still classified via
        `NativeEntry.is_reparse_point` -- callers MUST check this flag and
        must never pass such an entry's name to `open_child` -- but the rest
        of the listing (siblings unaffected by that one reparse point) is
        still returned instead of being discarded wholesale. `open_child`
        independently re-checks every opened entry for
        `FILE_ATTRIBUTE_REPARSE_POINT` regardless of this flag, so a caller
        that ignores `is_reparse_point` still fails closed rather than
        silently following the reparse point.
        """
        if self._handle is None:
            raise InputViolation("unreadable_input", "native handle is already closed")
        found: list[NativeEntry] = []
        buffer_size = 64 * 1024
        buffer = ctypes.create_string_buffer(buffer_size)
        base = ctypes.addressof(buffer)
        entry_header_size = ctypes.sizeof(FILE_ID_BOTH_DIR_INFORMATION)
        restart = True
        while True:
            io_status = IO_STATUS_BLOCK()
            status = _NtQueryDirectoryFile(
                self._handle,
                None,
                None,
                None,
                ctypes.byref(io_status),
                buffer,
                buffer_size,
                FILE_ID_BOTH_DIRECTORY_INFORMATION,
                0,
                None,
                1 if restart else 0,
            )
            restart = False
            if status == STATUS_NO_MORE_FILES:
                break
            if status != STATUS_SUCCESS:
                _raise_native_failure("directory query", status)
            offset = 0
            while True:
                entry = FILE_ID_BOTH_DIR_INFORMATION.from_address(base + offset)
                name = ctypes.wstring_at(
                    base + offset + entry_header_size, entry.FileNameLength // 2
                )
                if name not in (".", ".."):
                    is_reparse_point = bool(entry.FileAttributes & FILE_ATTRIBUTE_REPARSE_POINT)
                    if is_reparse_point and reject_reparse_points:
                        raise InputViolation(
                            "symlink_not_allowed", "symbolic links are not accepted"
                        )
                    is_directory = bool(entry.FileAttributes & FILE_ATTRIBUTE_DIRECTORY)
                    found.append(
                        NativeEntry(
                            name=name,
                            is_directory=is_directory,
                            is_reparse_point=is_reparse_point,
                            size=int(entry.EndOfFile),
                        )
                    )
                if entry.NextEntryOffset == 0:
                    break
                offset += entry.NextEntryOffset
        return tuple(sorted(found, key=lambda item: item.name))

"""Add Tauthon support to Virtualenv."""

import logging
from abc import ABCMeta
from collections import OrderedDict
from pathlib import Path

from virtualenv.create.describe import PosixSupports, WindowsSupports
from virtualenv.create.via_global_ref.builtin.python2.python2 import Python2
from virtualenv.create.via_global_ref.builtin.ref import PathRefToDest, RefMust, RefWhen
from virtualenv.create.via_global_ref.builtin.via_global_self_do import ViaGlobalRefVirtualenvBuiltin


class Tau(ViaGlobalRefVirtualenvBuiltin, metaclass=ABCMeta):
    """Interpreter name"""

    @classmethod
    def can_describe(cls, interpreter):
        return interpreter.implementation == "Tauthon" and super().can_describe(interpreter)

    @classmethod
    def exe_stem(cls):
        return "tauthon"


class TauPosix(Tau, PosixSupports, metaclass=ABCMeta):
    """Create a Tauthon virtual environment on POSIX platforms"""

    @classmethod
    def _executables(cls, interpreter):
        host_exe = Path(interpreter.system_executable)
        major, minor = interpreter.version_info.major, interpreter.version_info.minor
        targets = OrderedDict((i, None) for i in ["tauthon", f"tauthon{major}", f"tauthon{major}.{minor}", host_exe.name])
        must = RefMust.COPY
        yield host_exe, list(targets.keys()), must, RefWhen.ANY


class TauWindows(Tau, WindowsSupports, metaclass=ABCMeta):
    """Create a Tauthon virtual environment on Windows"""

    @classmethod
    def _executables(cls, interpreter):
        # symlink of the Tauthon executables does not work reliably, copy always instead
        # - https://bugs.python.org/issue42013
        # - venv
        host = cls.host_python(interpreter)
        for path in (host.parent / n for n in {"tauthon.exe", host.name}):
            yield host, [path.name], RefMust.COPY, RefWhen.ANY
        # for more info on pythonw.exe see https://stackoverflow.com/a/30313091
        python_w = host.parent / "tauthonw.exe"
        yield python_w, [python_w.name], RefMust.COPY, RefWhen.ANY

    @classmethod
    def host_python(cls, interpreter):
        return Path(interpreter.system_executable)


class Tauthon(Tau, Python2, metaclass=ABCMeta):
    """Create a Tauthon virtual environment"""

    @classmethod
    def sources(cls, interpreter):
        yield from super().sources(interpreter)
        # include folder needed on Tauthon as we don't have pyenv.cfg
        host_include_marker = cls.host_include_marker(interpreter)
        if host_include_marker.exists():
            yield PathRefToDest(host_include_marker.parent, dest=lambda self, _: self.include)  # noqa: U101

    @classmethod
    def needs_stdlib_py_module(cls):
        return False

    @classmethod
    def host_include_marker(cls, interpreter):
        return Path(interpreter.system_include) / "Python.h"

    @property
    def include(self):
        # the pattern include the distribution name too at the end, remove that via the parent call
        return (self.dest / self.interpreter.install_path("headers")).parent

    @classmethod
    def modules(cls):
        return ["os", "_oserror"]  # landmark to set sys.prefix

    def ensure_directories(self):
        dirs = super().ensure_directories()
        host_include_marker = self.host_include_marker(self.interpreter)
        if host_include_marker.exists():
            dirs.add(self.include.parent)
        else:
            logging.debug("no include folders as can't find include marker %s", host_include_marker)
        return dirs


class TauthonPosixBase(Tauthon, TauPosix, metaclass=ABCMeta):
    """common to macOS framework builds and other POSIX Tauthon"""

    @classmethod
    def sources(cls, interpreter):
        yield from super().sources(interpreter)

        # check if the makefile exists and if so make it available under the virtual environment
        make_file = Path(interpreter.sysconfig["makefile_filename"])
        if make_file.exists() and str(make_file).startswith(interpreter.prefix):
            under_prefix = make_file.relative_to(Path(interpreter.prefix))
            yield PathRefToDest(make_file, dest=lambda self, s: self.dest / under_prefix)  # noqa: U100


class TauthonPosix(TauthonPosixBase):
    """Tauthon on POSIX"""
    @classmethod
    def can_describe(cls, interpreter):
        return super().can_describe(interpreter)

    @classmethod
    def sources(cls, interpreter):
        yield from super().sources(interpreter)
        # landmark for exec_prefix
        exec_marker_file, to_path, _ = cls.from_stdlib(cls.mappings(interpreter), "lib-dynload")
        yield PathRefToDest(exec_marker_file, dest=to_path)


class TauthonWindows(Tauthon, TauWindows):
    """Tauthon on Windows"""

    @classmethod
    def sources(cls, interpreter):
        yield from super().sources(interpreter)
        py27_dll = Path(interpreter.system_executable).parent / "tauthon27.dll"
        if py27_dll.exists():  # this might be global in the Windows folder in which case it's alright to be missing
            yield PathRefToDest(py27_dll, dest=cls.to_bin)

        libs = Path(interpreter.system_prefix) / "libs"
        if libs.exists():
            yield PathRefToDest(libs, dest=lambda self, s: self.dest / s.name)

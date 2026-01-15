# This file is a minimal clang-format sublime-integration. To install:
# - Put this file into your sublime Packages directory, e.g. on Linux:
#     ~/.config/sublime-text-2/Packages/User/clang-format-sublime.py
# - Add a key binding:
#     { "keys": ["ctrl+shift+c"], "command": "clang_format" },
#
# With this integration you can press the bound key and clang-format will
# format the current lines and selections for all cursor positions. The lines
# or regions are extended to the next bigger syntactic entities.
#
# It operates on the current, potentially unsaved buffer and does not create
# or save any files. To revert a formatting, just undo.

from __future__ import annotations
import os
import sys
import sublime
import sublime_plugin
import subprocess
import threading

from collections.abc import Callable
from sublime_lib import ActivityIndicator
from typing import override

PREF_CLANG_FORMAT_PATH = 'clang_format_path'
PREF_FILE_NAME = 'ClangFormat (%s).sublime-settings'
MISSING_BINARY_MESSAGE = 'ClangFormat\n\nTo format the code, either full path to the \
clang-format binary must be specified in the package settings or %s binary must be in the PATH!'


def start_thread(
    on_exit: Callable[[bytes], None], on_error: Callable[[bytes], None], popen_args: list[str], stdin: bytes
) -> threading.Thread:
    """
    Start a process in a new thread.

    Runs the given args in a subprocess.Popen, and then calls the function
    on_exit when the subprocess completes.
    on_exit is a callable object, and popen_args is a list/tuple of args that
    on_error when the subprocess throws an error
    would give to subprocess.Popen.
    """
    def run_in_thread(
        on_exit: Callable[[bytes], None], on_error: Callable[[bytes], None], popen_args: list[str]
    ) -> None:
        startupinfo = None
        # Don't let console window pop-up on Windows.
        if platform_name() == 'windows':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        process = subprocess.Popen(popen_args,  # noqa: S603
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   stdin=subprocess.PIPE,
                                   startupinfo=startupinfo)
        output, error = process.communicate(stdin)

        if error:
            on_error(error)
        else:
            on_exit(output)

    thread = threading.Thread(target=run_in_thread, args=(on_exit, on_error, popen_args))
    thread.start()
    # returns immediately after the thread starts
    return thread


def platform_name() -> str:
    if 'linux' in sys.platform:
        return 'linux'
    elif 'darwin' in sys.platform:
        return 'mac'
    return 'windows'


def settings_filename() -> str:
    if 'linux' in sys.platform:
        return PREF_FILE_NAME % 'Linux'
    if 'darwin' in sys.platform:
        return PREF_FILE_NAME % 'OSX'
    return PREF_FILE_NAME % 'Windows'


def binary_name() -> str:
    if 'win32' in sys.platform:
        return 'clang-format.exe'
    return 'clang-format'


# Change this to format according to other formatting styles
# (see clang-format -help).
style = 'Chromium'


def is_exe(fpath: str) -> bool:
    return os.path.isfile(fpath) and os.access(fpath, os.X_OK)


def which(program: str) -> str | None:
    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ['PATH'].split(os.pathsep):
            exe_file = os.path.join(path.strip('"'), program)
            if is_exe(exe_file):
                return exe_file

    return None


class ClangFormatCommand(sublime_plugin.TextCommand):
    def __init__(self, view: sublime.View):
        super().__init__(view)
        self._indicator = None

    @override
    def run(self, edit: sublime.Edit, only_selection: bool=True):
        settings = sublime.load_settings(settings_filename())
        binary_path: str | None = settings.get(PREF_CLANG_FORMAT_PATH)
        if not binary_path:
            binary_path = which(binary_name())
            if not binary_path or not is_exe(binary_path):
                sublime.message_dialog(MISSING_BINARY_MESSAGE % binary_name())
                return

        args = [binary_path, '-fallback-style', style]
        file_name = self.view.file_name()
        if file_name:
            args.extend(['-assume-filename', file_name])
        else:
            print('Checking style without knowing file type. Results might be innacurate!')

        if only_selection:
            for region in self.view.sel():
                region_offset = min(region.a, region.b)
                region_length = abs(region.b - region.a)
                args.extend(['-offset', str(region_offset), '-length', str(region_length)])

        buffer_text = self.view.substr(sublime.Region(0, self.view.size()))
        encoding = self.view.encoding()
        encoding = encoding if encoding != 'Undefined' else 'utf-8'
        stdin = buffer_text.encode(encoding)
        viewport_pos = self.view.viewport_position()
        # Show progress indicator if formatting takes longer than 1s.
        self._indicator = ActivityIndicator(self.view, 'ClangFormat: Formatting...')
        sublime.set_timeout(self.start_indicator, 1000)

        start_thread(
            lambda output: self.on_formatting_success(viewport_pos, output, encoding),
            self.on_formatting_error,
            args,
            stdin
        )

    def on_formatting_success(self, viewport_pos, output: bytes, encoding: str) -> None:
        self.stop_indicator()
        self.view.run_command('clang_format_apply', {
            'output': output.decode(encoding),
            'viewport_pos': viewport_pos,
        })

    def on_formatting_error(self, error: bytes) -> None:
        self.stop_indicator()
        self.view.window().status_message('ClangFormat: Formatting error: %s' % error.decode('utf-8'))

    def start_indicator(self) -> None:
        if self._indicator:
            self._indicator.start()

    def stop_indicator(self) -> None:
        if self._indicator:
            self._indicator.stop()
            self._indicator = None


class ClangFormatApplyCommand(sublime_plugin.TextCommand):

    @override
    def run(self, edit: sublime.Edit, output: str, viewport_pos):
        self.view.window().status_message('ClangFormat: Formatted')
        self.view.replace(edit, sublime.Region(0, self.view.size()), output)
        # FIXME: Without the 10ms delay, the viewport sometimes jumps.
        sublime.set_timeout_async(lambda: self.view.set_viewport_position(viewport_pos, False), 10)

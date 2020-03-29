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

import os
import sys
import sublime
import sublime_plugin
import subprocess
import threading

PREF_CLANG_FORMAT_PATH = 'clang_format_path'
PREF_FILE_NAME = 'SublimeClangFormat (%s).sublime-settings'
MISSING_BINARY_MESSAGE = 'SublimeClangFormat\n\nTo format the code, either full path to the \
clang-format binary must be specified in the package settings or %s binary must be in the PATH!'


def run_command(on_exit, on_error, popen_args, stdin):
    """
    Runs the given args in a subprocess.Popen, and then calls the function
    on_exit when the subprocess completes.
    on_exit is a callable object, and popen_args is a list/tuple of args that
    on_error when the subprocess throws an error
    would give to subprocess.Popen.
    """
    def run_in_thread(on_exit, on_error, popen_args):
        startupinfo = None
        # Don't let console window pop-up on Windows.
        if platform_name() == 'windows':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        process = subprocess.Popen(popen_args,
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


def platform_name():
    if 'linux' in sys.platform:
        return 'linux'
    elif 'darwin' in sys.platform:
        return 'mac'
    return 'windows'


def settings_filename():
    if 'linux' in sys.platform:
        return PREF_FILE_NAME % 'Linux'
    elif 'darwin' in sys.platform:
        return PREF_FILE_NAME % 'OSX'
    return PREF_FILE_NAME % 'Windows'


def binary_name():
    if 'win32' in sys.platform:
        return 'clang-format.exe'
    return 'clang-format'


# Change this to format according to other formatting styles
# (see clang-format -help).
style = 'Chromium'


def is_exe(fpath):
    return os.path.isfile(fpath) and os.access(fpath, os.X_OK)


def which(program):
    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ['PATH'].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None


class ClangFormatCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        settings = sublime.load_settings(settings_filename())
        path = settings.get(PREF_CLANG_FORMAT_PATH)
        if path:
            binary_path = path
        else:
            binary_path = which(binary_name())
        if not binary_path or not is_exe(binary_path):
            sublime.message_dialog(MISSING_BINARY_MESSAGE % binary_name())
            return
        regions = []
        args = [binary_path, '-fallback-style', style]
        if self.view.file_name():
            args.extend(['-assume-filename', self.view.file_name()])
        else:
            print('Checking style without knowing file type. Results might be innacurate!')

        for region in self.view.sel():
            regions.append(region)
            region_offset = min(region.a, region.b)
            region_length = abs(region.b - region.a)
            args.extend(['-offset', str(region_offset), '-length', str(region_length)])

        buffer_text = self.view.substr(sublime.Region(0, self.view.size()))
        self.view.window().status_message('ClangFormat: Formatting...')
        encoding = self.view.encoding()
        encoding = encoding if encoding != 'Undefined' else 'utf-8'
        stdin = buffer_text.encode(encoding)
        viewport_pos = self.view.viewport_position()
        run_command(
            lambda output: self.on_formatting_success(viewport_pos, output, encoding),
            self.on_formatting_error,
            args,
            stdin
        )

    def on_formatting_success(self, viewport_pos, output, encoding):
        self.view.run_command('clang_format_apply', {
            'output': output.decode(encoding),
            'viewport_pos': viewport_pos,
        })

    def on_formatting_error(self, error):
        self.view.window().status_message('ClangFormat: Formatting error: %s' % error)


class ClangFormatApplyCommand(sublime_plugin.TextCommand):
    def run(self, edit, output, viewport_pos):
        self.view.window().status_message('ClangFormat: Formatted')
        self.view.replace(edit, sublime.Region(0, self.view.size()), output)
        # FIXME: Without the 10ms delay, the viewport sometimes jumps.
        sublime.set_timeout_async(lambda: self.view.set_viewport_position(viewport_pos, False), 10)

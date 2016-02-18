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

PREF_CLANG_FORMAT_PATH = 'clang_format_path'
PREF_FILE_NAME = 'SublimeClangFormat (%s).sublime-settings'


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
      sublime.message_dialog(
          'SublimeClangFormat\n\nTo format the code, either full path to the ' +
          'clang-format binary must be specified in the package settings or ' +
          binary_name() + ' binary must be in the PATH!')
      return
    encoding = self.view.encoding()
    if encoding == 'Undefined':
      encoding = 'utf-8'
    regions = []
    args = [binary_path, '-fallback-style', style]
    if self.view.file_name():
      args.extend(['-assume-filename', self.view.file_name()])
    else:
      print('Checking style without knowing file type. Results might be '
            'innacurate!')
    for region in self.view.sel():
      regions.append(region)
      region_offset = min(region.a, region.b)
      region_length = abs(region.b - region.a)
      args.extend(['-offset', str(region_offset),
                   '-length', str(region_length)])
    old_viewport_position = self.view.viewport_position()
    buf = self.view.substr(sublime.Region(0, self.view.size()))
    startupinfo = None
    # Don't let console window pop-up on Windows.
    if platform_name() == 'windows':
      startupinfo = subprocess.STARTUPINFO()
      startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
      startupinfo.wShowWindow = subprocess.SW_HIDE
    p = subprocess.Popen(args,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         stdin=subprocess.PIPE,
                         startupinfo=startupinfo)
    output, error = p.communicate(buf.encode(encoding))
    if not error:
      self.view.replace(edit,
                        sublime.Region(0, self.view.size()),
                        output.decode(encoding))
      # FIXME: Without the 10ms delay, the viewport sometimes jumps.
      sublime.set_timeout(lambda: self.view.set_viewport_position(
          old_viewport_position, False), 10)
    else:
      print(error)

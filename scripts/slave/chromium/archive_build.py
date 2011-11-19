#!/usr/bin/python
# Copyright (c) 2011 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A tool to archive a build and its symbols, executed by a buildbot slave.

  This script is used for developer builds.

  When this is run, the current directory (cwd) should be the outer build
  directory (e.g., chrome-release/build/).

  For a list of command-line options, call this script with '--help'.
"""

import glob
import optparse
import os
import platform
import simplejson
import sys
import re

from common import chromium_utils
from slave import slave_utils

import config


# The names of the files containing the list of files, symbols and tests to be
# archived for the build. This file can be present in self._tool_dir as well
# as in the path specifed by --extra-archive-paths.
ARCHIVE_FILE_NAME = 'FILES'
SYMBOL_FILE_NAME = 'SYMBOLS'
TEST_FILE_NAME = 'TESTS'


class StagingError(Exception):
  pass
  
class GSUtilError(Exception):
  pass


def ExpandWildcards(base_dir, path_list):
  """Accepts a list of paths relative to base_dir and replaces wildcards.

  Uses glob to change all file paths containing wild cards into lists
  of files present on the file system at time of calling.
  """
  if not path_list:
    return []

  regex = re.compile('[*?[]')

  returned_paths = []
  for path_fragment in path_list:
    if regex.search(path_fragment):
      globbed_paths = glob.glob(os.path.join(base_dir, path_fragment))
      new_paths = [
          globbed_path[len(base_dir)+1:] for globbed_path in globbed_paths
          if not os.path.isdir(globbed_path) ]
      returned_paths.extend(new_paths)
    else:
      returned_paths.append(path_fragment)

  return returned_paths


def ExtractDirsFromPaths(path_list):
  """Extracts a list of unique directory names from a list of paths.

  Given a list of relative paths, e.g. ['foo.txt', 'baz\\bar', 'baz\\bee.txt']
  returns a list of the directories therein (e.g. ['baz']). Does not
  include duplicates in the list.
  """
  dirs = set()
  for path in path_list:
    dir_name = os.path.dirname(path)
    if dir_name:
      dirs.add(dir_name)
  return list(dirs)


def _GetXMLChangeLogByModule(module_name, module_src_dir,
                             last_revision, current_revision):
  """Get the change log information for specified module and start/end
  revision.
  """
  if (last_revision and current_revision > last_revision):
    command = [slave_utils.SubversionExe(), 'log', module_src_dir,
                '--xml', '-r', '%d:%d' % (last_revision + 1, current_revision)]
    changelog = chromium_utils.GetCommandOutput(command)
    changelog_description = '%s changeLogs from ]%d to %d]' % (
        module_name, last_revision, current_revision)
  else:
    changelog = ''
    changelog_description = 'No new ChangeLogs on %s' % (module_name)
  return (changelog, changelog_description)


def Write(file_path, data):
  f = open(file_path, 'w')
  try:
    f.write(data)
  finally:
    f.close()


def MyCopyFileToGS(filename, gs_base, gs_subdir, mimetype=None):
  status = slave_utils.GSUtilCopyFile(filename,
                                      gs_base,
                                      gs_subdir,
                                      mimetype)
  if status != 0:
    dest = gs_base + '/' + gs_subdir
    raise GSUtilError('GSUtilCopyFile error %d. "%s" -> "%s"' % (status,
                                                                 filename,
                                                                 dest))


class StagerBase(object):
  """Handles archiving a build. Call the public ArchiveBuild() method."""

  def __init__(self, options, build_revision):
    """Sets a number of file and directory paths for convenient use."""

    self.options = options
    self._src_dir = os.path.abspath(options.src_dir)
    self._chrome_dir = os.path.join(self._src_dir, 'chrome')
    # TODO: This scode should not be grabbing so deeply into WebKit.
    #       Worse, this code ends up looking at top-of-tree WebKit
    #       instead of the revision in DEPS.
    self._webkit_dir = os.path.join(self._src_dir, 'third_party', 'WebKit',
                                    'Source', 'WebCore')
    self._v8_dir = os.path.join(self._src_dir, 'v8')
    # TODO: need to get the build *output* directory passed in instead so Linux
    # and Mac don't have to walk up a directory to get to the right directory.
    if chromium_utils.IsWindows():
      self._build_dir = os.path.join(options.build_dir, options.target)
      self._tool_dir = os.path.join(self._chrome_dir, 'tools', 'build', 'win')
    elif chromium_utils.IsLinux():
      self._build_dir = os.path.join(os.path.dirname(options.build_dir),
                                     'out', options.target)
      self._tool_dir = os.path.join(self._chrome_dir, 'tools', 'build', 'linux')
    elif chromium_utils.IsMac():
      self._build_dir = os.path.join(os.path.dirname(options.build_dir),
                                     'xcodebuild', options.target)
      self._tool_dir = os.path.join(self._chrome_dir, 'tools', 'build', 'mac')
    else:
      raise NotImplementedError(
          'Platform "%s" is not currently supported.' % sys.platform)
    self._staging_dir = slave_utils.GetStagingDir(self._src_dir)

    self._symbol_dir_base = options.dirs['symbol_dir_base']
    self._www_dir_base = options.dirs['www_dir_base']
    self._build_name = slave_utils.SlaveBuildName(self._src_dir)
    self._symbol_dir_base = os.path.join(self._symbol_dir_base,
                                         self._build_name)
    self._www_dir_base = os.path.join(self._www_dir_base, self._build_name)

    self._version_file = os.path.join(self._chrome_dir, 'VERSION')
    self._installer_file = os.path.join(self._build_dir,
        self.options.installer)

    if options.default_chromium_revision:
      self._chromium_revision = options.default_chromium_revision
    else:
      self._chromium_revision = slave_utils.SubversionRevision(self._chrome_dir)
    if options.default_webkit_revision:
      self._webkit_revision = options.default_webkit_revision
    else:
      self._webkit_revision = slave_utils.SubversionRevision(self._webkit_dir)
    if options.default_v8_revision:
      self._v8_revision = options.default_v8_revision
    else:
      self._v8_revision = slave_utils.SubversionRevision(self._v8_dir)
    self.last_change_file = os.path.join(self._staging_dir, 'LAST_CHANGE')
    # The REVISIONS file will record the revisions information of the main
    # components Chromium/WebKit/V8.
    self.revisions_path = os.path.join(self._staging_dir, 'REVISIONS')
    self._build_revision = build_revision
    # Will be initialized in GetLastBuildRevision.
    self.last_chromium_revision = None
    self.last_webkit_revision = None
    self.last_v8_revision = None

    self._symbol_files = self.BuildOldFilesList(SYMBOL_FILE_NAME)
    self._test_files = self.BuildOldFilesList(TEST_FILE_NAME)

    self._dual_upload = options.factory_properties.get('dual_upload', False)

  def BuildOldFilesList(self, source_file_name):
    """Build list of files from the old "file of paths" style input.

    Combine any source_file_name inputs found in the default tools dir and in
    any dirs given with --extra-archive-paths.
    """
    default_source = os.path.join(self._tool_dir, source_file_name)
    if os.path.exists(default_source):
      file_list = open(default_source).readlines()
    else:
      print 'WARNING: No default %s list found at %s' % (source_file_name,
                                                         default_source)
      file_list = []
    file_list = [f.strip() for f in file_list]
    file_list.extend(self.GetExtraFiles(self.options.extra_archive_paths,
                                        source_file_name))
    file_list = ExpandWildcards(self._build_dir, file_list)
    return file_list

  def ParseFilesList(self, buildtype, arch):
    """Determine the list of archive files for a given release.

    NOTE: A version of this handling is also in
    build-internal/scripts/slave-internal/branched/stage_build.py
    so be sure to update that if this is updated.
    """
    files_file = os.path.join(self._tool_dir, 'FILES.cfg')
    if not os.path.exists(files_file):
      raise StagingError('Files list does not exist (%s).' % files_file)
    exec_globals = {'__builtins__': None}

    files_list = None
    execfile(files_file, exec_globals)
    files_list = [
        fileobj['filename'] for fileobj in exec_globals['FILES']
        if (buildtype in fileobj['buildtype'] and arch in fileobj['arch'] and
            not fileobj.get('archive'))
    ]
    return files_list

  def MyCopyFileToDir(self, filename, destination, gs_base, gs_subdir='',
                      mimetype=None):
    if gs_base:
      MyCopyFileToGS(filename, gs_base, gs_subdir, mimetype)

    if not gs_base or self._dual_upload:
      chromium_utils.CopyFileToDir(filename, destination)

  def MyMaybeMakeDirectory(self, destination, gs_base):
    if not gs_base or self._dual_upload:
      chromium_utils.MaybeMakeDirectory(destination)

  def MyMakeWorldReadable(self, destination, gs_base):
    if not gs_base or self._dual_upload:
      chromium_utils.MakeWorldReadable(destination)

  def MySshMakeDirectory(self, host, destination, gs_base):
    if not gs_base or self._dual_upload:
      chromium_utils.SshMakeDirectory(host, destination)

  def MySshCopyFiles(self, filename, host, destination, gs_base,
                     gs_subdir=None, mimetype=None):
    if gs_base:
      MyCopyFileToGS(filename, gs_base, gs_subdir, mimetype)
    if not gs_base or self._dual_upload:
      chromium_utils.SshCopyFiles(filename, host, destination)

  def GetExtraFiles(self, extra_archive_paths, source_file_name):
    """Returns a list of extra files to package in the build output directory.

    For each of the paths in the extra_file_paths list, this function
    checks to see if path\source_file_name exists. If so, it expects these
    files to contain a list of newline-separated filenames that it returns
    in a list. The paths in extra_archive_paths are relative to the
    directory specified by --src-dir.
    """
    extra_files_list = []
    extra_path_list = extra_archive_paths.split(',')
    for path in extra_path_list:
      path = path.strip()
      source_file = os.path.join(self._src_dir, path, source_file_name)
      if os.path.exists(source_file):
        new_files_list = open(source_file).readlines()
        extra_files_list.extend(new_files_list)

    extra_files_list = [e.strip() for e in extra_files_list]
    extra_files_list = ExpandWildcards(self._build_dir, extra_files_list)
    return extra_files_list

  def GenerateRevisionFile(self):
    """Save chromium/webkit/v8's revision in a specified file. we will write a
    human readable format to save the revision information. The contents will be
    {"chromium_revision":chromium_revision,
     "webkit_revision":webkit_revision,
     "v8_revision":v8_revision}
    It is also in json format.
    """

    print 'Saving revision to %s' % self.revisions_path
    Write(
        self.revisions_path,
        ('{"chromium_revision":%d, "webkit_revision":%d, '
         '"v8_revision":%d}') % (self._chromium_revision,
                                 self._webkit_revision,
                                 self._v8_revision))

  def GetLastBuildRevision(self):
    """Reads the last staged build revision from last_change_file.

    If the last_change_file does not exist, returns None.
    We also try to get the last Chromium/WebKit/V8 revision from the REVISIONS
    file generated by GenerateRevisionFile
    """
    last_build_revision = None
    if os.path.exists(self.last_change_file):
      last_build_revision = int(open(self.last_change_file).read())

    if os.path.exists(self.revisions_path):
      fp = open(self.revisions_path)
      try:
        line = fp.readline()

        # TODO(markhuang): remove this block after all builders are updated
        line = line.replace('\'', '"')

        revisions_dict = simplejson.loads(line)
        if revisions_dict:
          self.last_chromium_revision = revisions_dict['chromium_revision']
          self.last_webkit_revision = revisions_dict['webkit_revision']
          self.last_v8_revision = revisions_dict['v8_revision']
      except (IOError, KeyError, ValueError), e:
        self.last_chromium_revision = None
        self.last_webkit_revision = None
        self.last_v8_revision = None
        print e
      fp.close()
    return last_build_revision

  def SaveBuildRevisionToSpecifiedFile(self, file_path):
    """Save build revision in the specified file"""

    print 'Saving revision to %s' % file_path
    Write(file_path, '%d' % self._build_revision)

  def _BuildVersion(self):
    """Returns the full build version string constructed from information in
    _version_file.  Any segment not found in that file will default to '0'.
    """
    major = 0
    minor = 0
    build = 0
    patch = 0
    for line in open(self._version_file, 'r'):
      line = line.rstrip()
      if line.startswith('MAJOR='):
        major = line[6:]
      elif line.startswith('MINOR='):
        minor = line[6:]
      elif line.startswith('BUILD='):
        build = line[6:]
      elif line.startswith('PATCH='):
        patch = line[6:]
    return '%s.%s.%s.%s' % (major, minor, build, patch)

  def _VerifyFiles(self):
    """Ensures that the needed directories and files are accessible.

    Returns a list of any that are not available.
    """
    not_found = []
    needed = self._archive_files
    needed = [os.path.join(self._build_dir, x.rstrip()) for x in needed]
    needed.append(self._version_file)
    # Add Windows installer.
    if chromium_utils.IsWindows():
      needed.append(self._installer_file)
    needed = self._RemoveIgnored(needed)
    for needed_file in needed:
      if not os.path.exists(needed_file):
        not_found.append(needed_file)
    return not_found

  def _GetDifferentialInstallerFile(self, version):
    """Returns the file path for incremental installer if present.

    Checks for file name of format *_<current version>_mini_installer.exe and
    returns the full path of first such file found.
    """
    path = os.path.join(self._build_dir,
                        '*%s_%s' % (version, self.options.installer))
    for f in glob.glob(path):
      return f
    return None

  def _RemoveIgnored(self, file_list):
    """Returns a list of the file paths in file_list whose filenames don't
    start with any of the strings in self.options.ignore.

    file_list may contain bare filenames or paths. For paths, only the base
    filename will be compared to to self.options.ignore.
    """
    def _IgnoreFile(filename):
      """Returns True if the filename starts with any of the strings in
      self.options.ignore.
      """
      for ignore in self.options.ignore:
        if filename.startswith(ignore):
          return True
      return False
    return [x for x in file_list if not _IgnoreFile(os.path.basename(x))]

  def CreateArchiveFile(self, zip_base_name, zip_file_list):
    """Put files into an archive dir as well as a zip of said archive dir.

    This method takes the list of files to archive, then prunes non-existing
    files from that list.

    If that list is empty CreateArchiveFile returns ('', '').
    Otherwise, this method returns the archive directory the files are
    copied to and the full path of the zip file in a tuple.

    TODO(robertshield): The returned zip_dir is never actually used -
    it seems like we could just get rid of it.
    """
    # Filter out files that don't exist.
    filtered_file_list = [f.strip() for f in zip_file_list if
                          os.path.exists(os.path.join(self._build_dir,
                                                      f.strip()))]

    if not filtered_file_list:
      # We have no files to archive, don't create an empty zip file.
      return ('', '')

    (zip_dir, zip_file) = chromium_utils.MakeZip(self._staging_dir,
                                                 zip_base_name,
                                                 filtered_file_list,
                                                 self._build_dir,
                                                 raise_error=False)
    if not os.path.exists(zip_file):
      raise StagingError('Failed to make zip package %s' % zip_file)
    return (zip_dir, zip_file)

  def _UploadSymbols(self, www_dir, gs_base):
    """Upload symbols to a share. It does not appear to upload symbols to a
       crash server.
       TODO(robertshield): Figure out if this should be uploading symbols to
       a crash server.
    """
    if chromium_utils.IsWindows():
      # Create a zip archive of the symbol files.  This must be done after the
      # main zip archive is created, or the latter will include this one too.
      sym_zip_file = self.CreateArchiveFile('chrome-win32-syms',
                                            self._symbol_files)[1]

      # symbols_copy should hold absolute paths at this point.
      # We avoid joining absolute paths because the version of python used by
      # the buildbots doesn't have the correct Windows os.path.join(), so it
      # doesn't understand C:/ and incorrectly concatenates the absolute paths.
      symbol_dir = os.path.join(self._symbol_dir_base,
                                str(self._build_revision))
      print 'chromium_utils.MaybeMakeDirectory(%s)' % symbol_dir
      print 'chromium_utils.CopyFileToDir(%s, %s)' % (sym_zip_file, symbol_dir)
      if not self.options.dry_run:
        self.MyMaybeMakeDirectory(symbol_dir, gs_base)
        self.MyCopyFileToDir(sym_zip_file, symbol_dir, gs_base)
    elif chromium_utils.IsLinux():
      # If there are no symbol files, then sym_zip_file will be an empty string.
      sym_zip_file = self.CreateArchiveFile('chrome-linux-syms',
                                            self._symbol_files)[1]
      if not sym_zip_file:
        print 'No symbols found, not uploading symbols'
        return 0
      if not self.options.dry_run:
        print 'SshMakeDirectory(%s, %s)' % (self.options.archive_host,
                                            www_dir)
        self.MySshMakeDirectory(self.options.archive_host, www_dir, gs_base)
        self.MyMakeWorldReadable(sym_zip_file, gs_base)
        self.MySshCopyFiles(sym_zip_file, self.options.archive_host, www_dir,
                            gs_base)
        os.unlink(sym_zip_file)
    elif chromium_utils.IsMac():
      # A Mac build makes fake dSYMs, so there is no point in collecting them.
      return 0
    else:
      raise NotImplementedError(
          'Platform "%s" is not currently supported.' % sys.platform)

  def _UploadBuild(self, www_dir, changelog_path, revisions_path,
                   archive_files, gs_base):
    if chromium_utils.IsWindows():
      print 'os.makedirs(%s)' % www_dir
      print 'chromium_utils.CopyFileToDir(%s, %s)' % (self._installer_file,
                                                      www_dir)
      for archive in archive_files:
        print 'chromium_utils.CopyFileToDir(%s, %s)' % (archive, www_dir)
      print 'chromium_utils.CopyFileToDir(%s, %s)' % (changelog_path, www_dir)
      print 'chromium_utils.CopyFileToDir(%s, %s)' % (revisions_path, www_dir)

      if not self.options.dry_run:
        self.MyMaybeMakeDirectory(www_dir, gs_base)
        self.MyCopyFileToDir(self._installer_file, www_dir, gs_base)
        for archive in archive_files:
          self.MyCopyFileToDir(archive, www_dir, gs_base)
        self.MyCopyFileToDir(changelog_path, www_dir, gs_base)
        self.MyCopyFileToDir(revisions_path, www_dir, gs_base)
    elif chromium_utils.IsLinux() or chromium_utils.IsMac():
      for archive in archive_files:
        print 'SshCopyFiles(%s, %s, %s)' % (archive,
                                            self.options.archive_host,
                                            www_dir)
      print 'SshCopyFiles(%s, %s, %s)' % (changelog_path,
                                          self.options.archive_host, www_dir)
      print 'SshCopyFiles(%s, %s, %s)' % (revisions_path,
                                          self.options.archive_host, www_dir)
      if not self.options.dry_run:
        print 'SshMakeDirectory(%s, %s)' % (self.options.archive_host,
                                            www_dir)
        self.MySshMakeDirectory(self.options.archive_host, www_dir, gs_base)
        for archive in archive_files:
          self.MyMakeWorldReadable(archive, gs_base)
          self.MySshCopyFiles(archive, self.options.archive_host, www_dir, gs_base)
          os.unlink(archive)
        # Files are created umask 077 by default, so make it world-readable
        # before pushing to web server.
        self.MyMakeWorldReadable(changelog_path, gs_base)
        self.MySshCopyFiles(changelog_path, self.options.archive_host, www_dir,
                            gs_base)
        self.MyMakeWorldReadable(revisions_path, gs_base)
        self.MySshCopyFiles(revisions_path, self.options.archive_host, www_dir,
                            gs_base)
    else:
      raise NotImplementedError(
          'Platform "%s" is not currently supported.' % sys.platform)

  def UploadTests(self, www_dir, gs_base):
    test_file_list = self._test_files
    if not test_file_list:
      return

    # Make test_file_list contain absolute paths.
    test_file_list = [os.path.join(self._build_dir, f) for f in test_file_list]
    UPLOAD_DIR = 'chrome-%s.test' % chromium_utils.PlatformName()

    # Filter out those files that don't exist.
    base_src_dir = os.path.join(self._build_dir, '')

    for test_file in test_file_list[:]:
      if os.path.exists(test_file):
        relative_dir = os.path.dirname(test_file[len(base_src_dir):])
        test_dir = os.path.join(www_dir, UPLOAD_DIR, relative_dir)
        print 'chromium_utils.CopyFileToDir(%s, %s)' % (test_file, test_dir)
      else:
        print '%s does not exist and is skipped.' % test_file
        test_file_list.remove(test_file)

    # Extract the list of test paths that will be created. These paths need
    # to be relative to the archive dir. We have to rebuild the relative
    # list from the now-pruned absolute test_file_list.
    relative_file_list = [tf[len(base_src_dir):] for tf in test_file_list]
    test_dirs = ExtractDirsFromPaths(relative_file_list)
    test_dirs = [os.path.join(www_dir, UPLOAD_DIR, d) for d in test_dirs]

    root_test_dir = os.path.join(www_dir, UPLOAD_DIR)
    print 'chromium_utils.MaybeMakeDirectory(%s)' % root_test_dir
    for test_dir in test_dirs:
      print 'chromium_utils.MaybeMakeDirectory(%s)' % test_dir

    if not self.options.dry_run:
      if chromium_utils.IsWindows():
        # Use Samba on Windows.
        self.MyMaybeMakeDirectory(root_test_dir, gs_base)
        for test_dir in test_dirs:
          self.MyMaybeMakeDirectory(test_dir, gs_base)
        for test_file in test_file_list:
          # TODO(robertshield): binaries and symbols are stored in a zip file
          # via CreateArchiveFile. Tests should be too.
          relative_dir = os.path.dirname(test_file[len(base_src_dir):])
          test_dir = os.path.join(www_dir, UPLOAD_DIR, relative_dir)
          self.MyCopyFileToDir(test_file, test_dir, gs_base,
                          '/'.join([UPLOAD_DIR, relative_dir]))
      else:
        # Otherwise use scp.
        self.MySshMakeDirectory(self.options.archive_host,
                                root_test_dir,
                                gs_base)
        for test_dir in test_dirs:
          self.MySshMakeDirectory(self.options.archive_host, test_dir, gs_base)
        for test_file in test_file_list:
          self.MyMakeWorldReadable(test_file, gs_base)
          # TODO(robertshield): binaries and symbols are stored in a zip file
          # via CreateArchiveFile. Tests should be too.
          relative_dir = os.path.dirname(test_file[len(base_src_dir):])
          test_dir = os.path.join(www_dir, UPLOAD_DIR, relative_dir)
          self.MySshCopyFiles(test_file, self.options.archive_host, test_dir,
                              gs_base, '/'.join([UPLOAD_DIR, relative_dir]))

  def _UploadFile(self, filename, www_dir, gs_base):
    path = os.path.join(self._build_dir, filename)
    if not os.path.exists(path):
      return
    if chromium_utils.IsWindows():
      print 'chromium_utils.CopyFileToDir(%s, %s)' % (path, www_dir)
      if not self.options.dry_run:
        self.MyCopyFileToDir(path, www_dir, gs_base)
    elif chromium_utils.IsLinux() or chromium_utils.IsMac():
      print 'SshCopyFiles(%s, %s, %s)' % (path, self.options.archive_host,
                                          www_dir)
      if not self.options.dry_run:
        self.MyMakeWorldReadable(path, gs_base)
        self.MySshCopyFiles(path, self.options.archive_host, www_dir, gs_base)

  def _GenerateChangeLog(self, previous_revision, changelog_path):
    """We need to generate change log for both chrome and webkit repository."""
    regex = re.compile(r'<\?xml.*\?>')

    if not previous_revision:
      changelog = 'Unknown previous build number: no change log produced.'
    else:
      # Generate Chromium changelogs
      (chromium_cl, chromium_cl_description) = _GetXMLChangeLogByModule(
          'Chromium', self._src_dir, self.last_chromium_revision,
          self._chromium_revision)
      # Remove the xml declaration since we need to combine  the changelogs
      # of both chromium and webkit.
      if chromium_cl:
        chromium_cl = regex.sub('', chromium_cl)

      # Generate WebKit changelogs
      (webkit_cl, webkit_cl_description) = _GetXMLChangeLogByModule(
          'WebKit', self._webkit_dir, self.last_webkit_revision,
          self._webkit_revision)
      # Remove the xml declaration since we need to combine  the changelogs
      # of both chromium and webkit.
      if webkit_cl:
        webkit_cl = regex.sub('', webkit_cl)

      # Generate V8 changelogs
      (v8_cl, v8_cl_description) = _GetXMLChangeLogByModule(
          'V8', self._v8_dir, self.last_v8_revision, self._v8_revision)
      # Remove the xml declaration since we need to combine the changelogs
      # of both chromium and webkit.
      if v8_cl:
        v8_cl = regex.sub('', v8_cl)

      # Generate the change logs.
      changelog = ('<?xml version=\"1.0\"?>\n'
                   '<changelogs>\n%s\n%s\n%s\n%s\n%s\n%s\n</changelogs>\n' % (
                      chromium_cl_description, chromium_cl,
                      webkit_cl_description, webkit_cl,
                      v8_cl_description, v8_cl))
    Write(changelog_path, changelog)

  def ArchiveBuild(self):
    """Zips build files and uploads them, their symbols, and a change log."""
    result = 0
    if self._build_revision is None:
      raise StagingError('No build revision was provided')
    print 'Staging in %s' % self._staging_dir

    arch = platform.architecture(bits='unknown')[0]
    if arch == 'unknown':
      raise StagingError('Could not determine build architecture')
    files_list = self.ParseFilesList(self.options.mode, arch)
    files_list = ExpandWildcards(self._build_dir, files_list)
    self._archive_files = files_list
    self._archive_files.extend(self.GetExtraFiles(
        self.options.extra_archive_paths, ARCHIVE_FILE_NAME))
    # Check files and revision numbers.
    not_found = self._VerifyFiles()
    print 'last change: %d' % self._build_revision
    previous_revision = self.GetLastBuildRevision()
    if self._build_revision <= previous_revision:
      # If there have been no changes, report it but don't raise an exception.
      # Someone might have pushed the "force build" button.
      print 'No changes since last build (r%d <= r%d)' % (self._build_revision,
                                                          previous_revision)
      return 0

    print 'build name: %s' % self._build_name

    archive_base_name = 'chrome-%s' % chromium_utils.PlatformName()
    archive_file = self.CreateArchiveFile(archive_base_name,
                                          self._archive_files)[1]

    # Generate a change log or an error message if no previous revision.
    changelog_path = os.path.join(self._staging_dir, 'changelog.xml')
    self._GenerateChangeLog(previous_revision, changelog_path)

    # Generate a revisions file which contains the Chromium/WebKit/V8's
    # revision information.
    self.GenerateRevisionFile()

    www_dir = os.path.join(self._www_dir_base, str(self._build_revision))
    gs_bucket = self.options.factory_properties.get('gs_bucket', None)
    gs_base = None
    if gs_bucket:
      gs_base = '/'.join([gs_bucket, self._build_name,
                          str(self._build_revision)])
    self._UploadSymbols(www_dir, gs_base)
    self._UploadBuild(www_dir, changelog_path, self.revisions_path,
                      [archive_file], gs_base)

    # Archive Linux packages (if any -- only created for Chrome builds).
    if chromium_utils.IsLinux():
      linux_packages = (glob.glob(os.path.join(
          self._build_dir, '*-r%s_*.deb' % self._chromium_revision)))
      linux_packages.extend(glob.glob(os.path.join(
          self._build_dir, '*-%s.*.rpm' % self._chromium_revision)))
      for package_file in linux_packages:
        print 'SshCopyFiles(%s, %s, %s)' % (package_file,
                                            self.options.archive_host,
                                            www_dir)
      if not self.options.dry_run:
        print 'SshMakeDirectory(%s, %s)' % (self.options.archive_host,
                                            www_dir)
        self.MySshMakeDirectory(self.options.archive_host, www_dir, gs_base)

        for package_file in linux_packages:
          self.MyMakeWorldReadable(package_file, gs_base)
          self.MySshCopyFiles(package_file, self.options.archive_host,
                         www_dir, gs_base)
          # Cleanup archived packages, otherwise they keep accumlating since
          # they have different filenames with each build.
          os.unlink(package_file)

    self.UploadTests(www_dir, gs_base)

    if not self.options.dry_run:
      # Save the current build revision locally so we can compute a changelog
      # next time
      self.SaveBuildRevisionToSpecifiedFile(self.last_change_file)

      # Record the latest revision in the developer archive directory.
      latest_file_path = os.path.join(self._www_dir_base, 'LATEST')
      if chromium_utils.IsWindows():
        print 'Saving revision to %s' % latest_file_path
        if gs_base:
          slave_utils.GSUtilCopyFile(self.last_change_file, gs_base, '..',
                                     mimetype='text/plain')
        if not gs_base or self._dual_upload:
          self.SaveBuildRevisionToSpecifiedFile(latest_file_path)
      elif chromium_utils.IsLinux() or chromium_utils.IsMac():
        # Files are created umask 077 by default, so make it world-readable
        # before pushing to web server.
        self.MyMakeWorldReadable(self.last_change_file, gs_base)
        print 'Saving revision to %s:%s' % (self.options.archive_host,
                                            latest_file_path)
        self.MySshCopyFiles(self.last_change_file, self.options.archive_host,
                            latest_file_path, gs_base, '..',
                            mimetype='text/plain')
      else:
        raise NotImplementedError(
              'Platform "%s" is not currently supported.' % sys.platform)

    # Upload extra build artifacts.
    # TODO(mmoss): This should be pulled from FILES.cfg. remoting-it2me.zip is
    # already in there. Need to add devtools_frontend.zip, then put in handling
    # here based on the 'archive' field.
    self._UploadFile('devtools_frontend.zip', www_dir, gs_base)
    self._UploadFile('remoting-it2me.zip', www_dir, gs_base)

    if len(not_found):
      sys.stderr.write('\n\nWARNING: File(s) not found: %s\n' %
                       ', '.join(not_found))
    return result


class StagerByChromiumRevision(StagerBase):
  """Handles archiving a build. Call the public ArchiveBuild() method.
  Archive a build according to its chromium revision if it is because of
  the chromium change.
  """

  def __init__(self, options):
    """Overwrite _build_revision for archiving build by Chromium revision."""

    StagerBase.__init__(self, options, None)
    self._build_revision = self._chromium_revision


class StagerByBuildNumber(StagerBase):
  """Handles archiving a build. Call the public ArchiveBuild() method.
  Archive a build according to the build number if it is because of
  the changes happened on multiple components like chromium/webkit/v8.
  """

  def __init__(self, options):
    """Overwrite _build_revision for archiving build by build number."""

    StagerBase.__init__(self, options, options.build_number)


def main(argv):
  option_parser = optparse.OptionParser()

  option_parser.add_option('--mode', default='dev',
      help='switch indicating how to archive build (dev is only valid value)')
  option_parser.add_option('--target', default='Release',
      help='build target to archive (Debug or Release)')
  option_parser.add_option('--src-dir', default='src',
                           help='path to the top-level sources directory')
  option_parser.add_option('--build-dir', default='chrome',
                           help='path to main build directory (the parent of '
                                'the Release or Debug directory)')
  option_parser.add_option('--extra-archive-paths', default='',
                           help='comma-separated lists of paths containing '
                                'files named FILES, SYMBOLS and TESTS. These '
                                'files contain lists of extra files to be '
                                'that will be archived. The paths are relative '
                                'to the directory given in --src-dir.')
  option_parser.add_option('--build-number', type='int',
                           help='The build number of the builder running '
                                'this script. we use it as the name of build '
                                'archive directory')
  option_parser.add_option('--default-chromium-revision', type='int',
                           help='The default chromium revision so far is only '
                                'used by archive_build unittest to set valid '
                                'chromium revision in test')
  option_parser.add_option('--default-webkit-revision', type='int',
                           help='The default webkit revision so far is only '
                                'used by archive_build unittest to set valid '
                                'webkit revision in test')
  option_parser.add_option('--default-v8-revision', type='int',
                           help='The default v8 revision so far is only '
                                'used by archive_build unittest to set valid '
                                'v8 revision in test')
  option_parser.add_option('--dry-run', action='store_true',
                           help='Avoid making changes, for testing')
  option_parser.add_option('--installer', default=config.Archive.installer_exe,
                           help='Installer executable name')
  option_parser.add_option('--ignore', default=[], action='append',
                           help='Files to ignore')
  option_parser.add_option('--archive_host',
                           default=config.Archive.archive_host)
  option_parser.add_option('--build-properties', action='callback',
                           callback=chromium_utils.convert_json, type='string',
                           nargs=1, default={},
                           help='build properties in JSON format')
  option_parser.add_option('--factory-properties', action='callback',
                           callback=chromium_utils.convert_json, type='string',
                           nargs=1, default={},
                           help='factory properties in JSON format')
  options, args = option_parser.parse_args()
  if args:
    raise StagingError('Unknown arguments: %s' % args)

  if not options.ignore:
    # Independent of any other configuration, these exes and any symbol files
    # derived from them (i.e., any filename starting with these strings) will
    # not be archived or uploaded, typically because they're not built for the
    # current distributon.
    options.ignore = config.Archive.exes_to_skip_entirely

  if options.mode == 'official':
    option_parser.error('Official mode is not supported here')
  elif options.mode == 'dev':
    options.dirs = {
      # Built files are stored here, in a subdir. named for the build version.
      'www_dir_base': config.Archive.www_dir_base + 'snapshots',

      # Symbols are stored here, in a subdirectory named for the build version.
      'symbol_dir_base': config.Archive.www_dir_base + 'snapshots',
    }
  else:
    option_parser.error('Invalid options mode %s' % options.mode)

  if options.build_number is not None:
    s = StagerByBuildNumber(options)
  else:
    s = StagerByChromiumRevision(options)
  return s.ArchiveBuild()


if '__main__' == __name__:
  sys.exit(main(None))

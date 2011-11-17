# Copyright (c) 2011 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from master import build_utils

from buildbot.changes import svnpoller

def ChromeTreeFileSplitter(path):
  """split_file for the 'src' project in the trunk."""

  # List of projects we are interested in. The project names must exactly
  # match paths in the Subversion repository, relative to the 'path' URL
  # argument. build_utils.SplitPath() will use them as branch names to
  # kick off the Schedulers for different projects.
  projects = ['trunk']
  return build_utils.SplitPath(projects, path)

def Update(config, active_master, c):
  # Polls config.Master.trunk_url for changes
  viewvc_url = "http://code.google.com/p/omaha/source/detail?r=%s"
  poller = svnpoller.SVNPoller(svnurl='http://omaha.googlecode.com/svn/',
                               split_file=ChromeTreeFileSplitter,
                               pollinterval=10,
                               revlinktmpl=viewvc_url)
  c['change_source'].append(poller)

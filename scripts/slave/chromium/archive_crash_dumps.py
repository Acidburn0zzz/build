#!/usr/bin/env python
# Copyright (c) 2011 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

""" A tool to archive crash dumps generated by buildbots running layout tests.
"""

import sys

def main():
  # The shell-script version of this tool, included below, doesn't work.  Rather
  # than fixing it, we should rewrite it in Python when we want to re-enable it.
  print "This tool needs to be rewritten before it can be enabled."
  return 0


if __name__ == '__main__':
  sys.exit(main())

# String has no effect.
# pylint: disable=W0105
"""

#!/bin/sh

# -----------------------------------------------------------------------------
# This script can be used to archive any crash dumps generated while running
# the layout tests.  A directory is created with the name of the latest CL
# and the crash dumps are copied to it.

if [ $# = 0 ]; then
  echo "usage: $(basename $0) output_dir"
  exit 1
fi

exec_dir=$(dirname $0)
# path to chrome dir for example c:\b\chrome\chrome-release-jsc\build\chrome
base_dir=$(cygpath -a "$exec_dir"/../../.. | sed 's/\(.*\)\/$/\1/')
dump_dir=$(cygpath -a "$base_dir"/../data/webkit/LayoutTests/ | sed 's/\(.*\)\/$/\1/')

# -----------------------------------------------------------------------------
# Get the last CL number
last_change() {
  cd chrome
  $base_dir/../third_party/svn/svn.exe info | grep 'Revision:' | cut -d' ' -f2 | tr -d '\r'
  cd ..
}

# -----------------------------------------------------------------------------

last_cl=$(last_change)
echo "last change: $last_cl"
echo "host name: $(hostname)"

# Check if there are any crash dumps.
dumps=$(ls "$dump_dir"/*.dmp)
if [ "$dumps" = "" ]; then
  exit 0
fi

mode=${2:-Release}
build_name=`echo $base_dir | sed "s/\(.*\)\(chrome-$mode[^\\\/]*\)\(.*\)/\2/"`

"$base_dir/tools/build/win/map_drive.bat" "Q:"
chrome_dev_dir=$(cygpath -a "Q:")
output_dir="$chrome_dev_dir/$1/$build_name/$last_cl"

mkdir -p "$output_dir"
cp -f "$dump_dir"/*.dmp "$output_dir"

# now, for the symbols:
syms_dir="$output_dir/chrome-win32.syms"
mkdir -p "$syms_dir"

# it sucks to hard code these pdb files here
for p in test_shell; do
  cp -f "$base_dir/$mode/$p.pdb" "$syms_dir"
done

"""

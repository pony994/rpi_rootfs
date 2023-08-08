#!/usr/bin/env python3

import os
import subprocess
import sys
import re
import errno

# Syncing Directory/File Pattern
RSYNC_INCLUDE = ['etc/', 'lib/', 'usr/', 'opt/vc']
RSYNC_CMD = ['/usr/bin/rsync']
RSYNC_OPTIONS = ['-rRlvu', '--stats', '--delete-after']
EXCLUDE_PATH_PATTERN = r'/proc/*|/dev/*'


# Error code from rsync manual page
def rsync_err_msg(retcode):
    errorcode_to_msg = {
        1: "Syntax or usage error",
        2: "Protocol incompatibility",
        3: "Errors selecting input/output files, dirs",
        4: "Requested  action not supported",
        5: "Error starting client-server protocol",
        6: "Daemon unable to append to log-file",
        10: "Error in socket I/O",
        11: "Error in file I/O",
        12: "Error in rsync protocol data stream",
        13: "Errors with program diagnostics",
        14: "Error in IPC code",
        20: "Received SIGUSR1 or SIGINT",
        21: "Some error returned by waitpid()",
        22: "Error allocating core memory buffers",
        23: "Partial transfer due to error",
        24: "Partial transfer due to vanished source files",
        25: "The --max-delete limit stopped deletions",
        30: "Timeout in data send/receive",
        35: "Timeout waiting for daemon connection",
    }
    return errorcode_to_msg.get(retcode, "error code not found")


def rsync_get_include_option(user):
    return f"{user}:/{{','.join(RSYNC_INCLUDE)}}"


def process_rsync_rootfs(user, path):
    rsync_full_command = RSYNC_CMD + RSYNC_OPTIONS + [
        "--include-from=data/rsync_include_list.txt",
        "--exclude-from=data/rsync_exclude_list.txt",
        rsync_get_include_option(user), path]
    print(rsync_full_command)
    ret = subprocess.call(rsync_full_command, shell=False)
    if ret != 0:
        print(f"Rsync error : {rsync_err_msg(ret)}")
    return ret


def relativelinks_handlelink(topdir, filep, subdir):
    link = os.readlink(filep)

    if link[0] != "/" or link.startswith(topdir):
        return

    os.unlink(filep)
    os.symlink(os.path.relpath(topdir + link, subdir), filep)


def process_relativelinks(path):
    topdir = os.path.abspath(path)

    for subdir, dirs, files in os.walk(topdir):
        if any(re.findall(EXCLUDE_PATH_PATTERN, subdir, re.IGNORECASE)):
            continue
        for f in files:
            filep = os.path.join(subdir, f)
            if os.path.islink(filep):
                relativelinks_handlelink(topdir, filep, subdir)


def symlink_force(target, link_name):
    try:
        os.symlink(target, link_name)
    except OSError as e:
        if e.errno == errno.EEXIST:
            os.remove(link_name)
            os.symlink(target, link_name)
        else:
            print(f"Error: {e} -- target:\"{target}\", link_name:\"{link_name}\"")


def process_pkgconfig_link(path):
    pkgconfig_path = os.path.abspath(path) + '/usr/lib/arm-linux-gnueabihf/pkgconfig'
    if os.path.exists(pkgconfig_path):
        print(f"pkg config: {pkgconfig_path}")
        for subdir, dirs, files in os.walk(pkgconfig_path):
            for f in files:
                filep = os.path.join(subdir, f)
                target_packageconfig = "../../lib/arm-linux-gnueabihf/pkgconfig/" + f
                link_packageconfig = os.path.abspath(path) + "/usr/share/pkgconfig/" + f
                print(f"source {target_packageconfig} target {link_packageconfig}")
                symlink_force(target_packageconfig, link_packageconfig)
    else:
        sys.stderr.write(f'ERROR: pkg-config does not exist : {pkgconfig_path}\n\n')


def inplace_change(filename, old_string, new_string):
    with open(filename) as f:
        s = f.read()
        if old_string not in s:
            print(f'"{old_string}" not found in {filename}.')
            return

    with open(filename, 'w') as f:
        print(f'Changing "{old_string}" to "{new_string}" in {filename}')
        s = s.replace(old_string, new_string)
        f.write(s)


def fix_process_ld_scripts(path, filename):
    if not os.path.exists(filename):
        print(f"linker script file does not exist: {filename}")
        return
    new_content = f"{os.path.abspath(path)}/usr/lib/arm-linux-gnueabihf/"
    inplace_change(filename, 'GROUP (', f'GROUP ({new_content}')


def process_ld_scripts(path):
    ldscripts = ['libbfd.so', 'libopcodes.so']
    for ldscript in ldscripts:
        ldscript_path = f"{path}/usr/lib/{ldscript}"
        fix_process_ld_scripts(path, ldscript_path)


def main(argv):
    if len(argv) != 3:
        sys.stderr.write(
            f'Usage: {argv[0]} [<user@hostname>|local] <rootfs path>\n'
            '\tuser@hostname : Rpi host address and user information for rcp connection\n'
            '\tlocal : Performs fixing processes without image copying.\n')
        return 1

    if not sys.platform.startswith('linux'):
        sys.stderr.write(f'RPi RootFS does not support this platform: {sys.platform}\n\n')
        return 1

    sync_image_url = argv[1]
    rootfs_path = argv[2]

    if sync_image_url != 'local':
        print("################################################################################")
        print(f"###\n### rootfs syncing from {argv[1]}\n###")
        ret = process_rsync_rootfs(sync_image_url, rootfs_path)
        if ret != 0:
            return 1

    print("################################################################################")
    print(f"###\n### rootfs fixing start for path {rootfs_path}\n###")

    print("Relative linking process")
    process_relativelinks(rootfs_path)
    print("pkg-config symbolic link process")
    process_pkgconfig_link(rootfs_path)
    print("LD Scripts Process")
    process_ld_scripts(rootfs_path)
    print("done")

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""
    Host application of the browser extension PassFF
    that wraps around the zx2c4 pass script.
"""

import json
import os
import struct
import subprocess
import sys
import re

VERSION = "_VERSIONHOLDER_"

###############################################################################
######################## Begin preferences section ############################
###############################################################################
COMMAND = "pass"
COMMAND_ARGS = []
COMMAND_ENV = {
    "TREE_CHARSET": "ISO-8859-1",
    "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
}
CHARSET = "UTF-8"

###############################################################################
######################### End preferences section #############################
###############################################################################


def getMessage():
    """ Read a message from stdin and decode it. """
    rawLength = sys.stdin.buffer.read(4)
    if len(rawLength) == 0:
        sys.exit(0)
    messageLength = struct.unpack('@I', rawLength)[0]
    message = sys.stdin.buffer.read(messageLength).decode("utf-8")
    return json.loads(message)


def encodeMessage(messageContent):
    """ Encode a message for transmission, given its content. """
    encodedContent = json.dumps(messageContent)
    encodedLength = struct.pack('@I', len(encodedContent))
    return {'length': encodedLength, 'content': encodedContent}


def sendMessage(encodedMessage):
    """ Send an encoded message to stdout. """
    sys.stdout.buffer.write(encodedMessage['length'])
    sys.stdout.write(encodedMessage['content'])
    sys.stdout.flush()

def mk_tmp_bashrc(path_to_bashrc):
    try:
        with open(path_to_bashrc) as fd:
            lines = fd.readlines()
            no_ansi_lines = filter(
                          lambda x: (not re.search(r"echo.+-ne",x)),
                          lines)
            path_to_tmprc = os.path.dirname(path_to_bashrc)+\
                            os.path.sep+".tmp.bashrc"
            with open(path_to_tmprc,"w") as tmpfd:
                tmpfd.writelines(no_ansi_lines)
            return path_to_tmprc
    except OSError:
        return None


if __name__ == "__main__":
    # Read message from standard input
    receivedMessage = getMessage()
    opt_args = []
    pos_args = []
    std_input = None

    if len(receivedMessage) == 0:
        opt_args = ["show"]
        pos_args = ["/"]
    elif receivedMessage[0] == "insert":
        opt_args = ["insert", "-m"]
        pos_args = [receivedMessage[1]]
        std_input = receivedMessage[2]
    elif receivedMessage[0] == "generate":
        opt_args = ["generate"]
        pos_args = [receivedMessage[1], receivedMessage[2]]
        if "-n" in receivedMessage[3:]:
            opt_args.append("-n")
    elif receivedMessage[0] == "grepMetaUrls" and len(receivedMessage) == 2:
        opt_args = ["grep", "-iE"]
        url_field_names = receivedMessage[1]
        pos_args = ["^({}):".format('|'.join(url_field_names))]
    elif receivedMessage[0] == "otp" and len(receivedMessage) == 2:
        opt_args = ["otp"]
        key = receivedMessage[1]
        key = "/" + (key[1:] if key[0] == "/" else key)
        pos_args = [key]
    else:
        opt_args = ["show"]
        key = receivedMessage[0]
        key = "/" + (key[1:] if key[0] == "/" else key)
        pos_args = [key]
    opt_args += COMMAND_ARGS

    # Set up (modified) command environment
    env = dict(os.environ)
    if "HOME" not in env:
        env["HOME"] = os.path.expanduser('~')
    for key, val in COMMAND_ENV.items():
        env[key] = val

    # Set up subprocess params
    cmd = [COMMAND] + opt_args + ['--'] + pos_args
    proc_params = {
        'input': bytes(std_input, CHARSET) if std_input else None,
        'stdout': subprocess.PIPE,
        'stderr': subprocess.PIPE,
        'env': env
    }

    if "nt" in os.name:
        path_to_posix_shell = None
        posix_opts = None
        where = subprocess.run(["where", "msys2"],
                                              stdout=subprocess.PIPE,
                                              stderr=subprocess.PIPE)
        try:
            path_to_posix_shell = os.path.dirname(where.stdout.decode(CHARSET).strip())\
                                                  +r"\usr\bin\bash.exe"
            tmprc = mk_tmp_bashrc(os.path.expanduser("~")+os.path.sep+".bashrc")
            if tmprc:
                tmprc = ["--rcfile", tmprc]
            else:
                tmprc = []
            posix_opts = tmprc + ["-l","-c"]
            where.check_returncode()
        except subprocess.CalledProcessError:
            where = subprocess.run(["where", "wsl"], stdout=subprocess.PIPE,
                                                     stderr=subprocess.PIPE)
            wsl_home = subprocess.run(["wsl","--","echo","$HOME"],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)\
                             .stdout.decode(CHARSET).strip()
            path_to_posix_shell = where.stdout.decode(CHARSET).strip()
            posix_opts = ["--rcfile",f"{wsl_home}/.bashrc","-i","-c"]

        posix_cmd = [path_to_posix_shell] + posix_opts + [" ".join(cmd)]
        proc = subprocess.run(posix_cmd, **proc_params)
        if proc.returncode == 0:
            sendMessage(
                encodeMessage({
                    "exitCode": proc.returncode,
                    "stdout": proc.stdout.decode(CHARSET),
                    "stderr": b''.decode(CHARSET),
                    "version": VERSION }))
            sys.exit(0)
    else:
        proc = subprocess.run(cmd, **proc_params)
    
    # Send response
    sendMessage(
        encodeMessage({
        "exitCode": proc.returncode,
        "stdout": proc.stdout.decode(CHARSET),
        "stderr": proc.stderr.decode(CHARSET),
        "version": VERSION
        }))

#!/usr/bin/python

ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: nfs_exports

short_description: Manipulate NFS export rules

version_added: "2.4"

description:
    - "Configure NFS exports on the local system"

options:
    name:
        description:
            - Descriptive text or other reference to be returned
        required: True
    action:
        description:
            - Select the operation to perform
        options:
            - add
            - remove
        required: True
    update:
        description:
            - Should the system be updated when this command finishes
        required: False
        default: True
    clear_all:
        description:
            - Discard all existing exports before applying the current action
        required: False
        default: False
    path:
        description:
            - The path on the local system to be exported (must exist already)
        required: For all except delete_all action.
    clients:
        description:
            - The client(s) that may use this export 
            - '*' is the special case of 'all clients'
            - a single hostname, ip address, net range, or wildcard
            - see exports(7) for full syntax
        required: For all except delete_all action.
    read_only:
        description:
            - if false then clients may read-write
        required: False
        default: True
    root_squash:
        description:
            - Map request from uid/gid 0 to the anonymous uid/gid
        required: False
        default: True
    all_squash:
        description:
            - Map all requests to the anonymous uid/gid
        required: False
        default: False
    security:
        description:
            - Colon delimited list of security flaours to negotiate
            - sys (No security)
            - krb5 (authentication only)
            - krb5i (krb5 + integrity protection)
            - krb5p (krb5i + privacy protection)
        required: False
        default: 'sys'
    options:
        description:
            - Any additional options not otherwise listed
            - See exports(5) for details
        required: False
        default: empty

extends_documentation_fragment:
    - azure

author:
    - Justin Mitchell (jumitche@redhat.com)
'''

EXAMPLES = '''
# Simply add one export immediately
- name: Simple Test
  nfs_exports:
    name: Adding a read-write mode share for one host
    action: add
    path: /share
    read-only: false
    update: true
    clients: 10.0.0.1/24

# remove all existing exports, add one
- name: Replace Test
  nfs_exports:
    name: Replace with one
    erase_all: true
    action: add
    path: /home
    clients: *

# replace existing exports with two new ones
- name: Multi Test
  nfs_exports:
    name: Clear and first export
    erase_all: true
    action: add
    path: /home
    clients: *
    read-only: false
    security: krb5p:krb5i:krb5
  nfs_exports:
    name: Second export and commit
    action: add
    path: /extras
    clients: *
    read-only: true
    update: true

# fail the module
- name: Test failure of the module
  my_new_test_module:
    name: fail me
'''

RETURN = '''
name:
    type: str
    description: The original name param that was passed in
message:
    type: str
    description: The output message that the sample module generates
error:
    type: str
    description: Detailed error description
'''

from ansible.module_utils.basic import AnsibleModule
import os
import shlex
import fcntl
import tempfile
import subprocess
from subprocess import CalledProcessError, check_output

_EXPORTS = "/etc/exports"
_EXPORTFS = "/usr/sbin/exportfs"

def _parse_options(optionstring):
    """ Parse a comma seperated option list into a dict """
    options = {}

    if optionstring is None:
        return options

    optionlist = optionstring.split(',')
    for opt in optionlist:
        if '=' in opt:
            key, val = opt.split('=')
        else:
            key = val = opt
        options[key] = val

    return options

def _print_options(optionset):
    """ Turn a dict of options into a comma seperated string """
    output = []

    if optionset is None:
        return None

    for key in sorted(optionset):
        if key == optionset[key]:
            output.append(key)
        else:
            output.append(key + '=' + optionset[key])

    if output:
        return ",".join(output)
    else:
        return None

def _parse_export(line=None):
    """ Parse a line of export file into seperate entries """

    if len(line) < 1:
        return []

    parts = shlex.split(line, '#')

    if len(parts) < 1:
        return []

    exports = []

    path = parts[0]
    for host in parts[1:]:
        optionstring = ''
        if '(' and ')' in host:
            if host[0] != '(':
                host, optionstring = host[:-1].split('(')
            else:
                optionstring = host[1:-1]
                host = '*'
        exports.append((path, host, optionstring))
    return exports

def _open_exports(canwrite, filename, result):
    if canwrite:
        mode = "r+"
    else:
        mode = "r"

    if not os.path.exists(filename):
        result['error'] = "file %s does not exist" % (filename)
        if canwrite:
            mode = "w"
        else:
            raise IOError

    try:
        efile = open(filename, mode)
    except IOError as err:
        result['error'] = "open %s failed: %s" % (filename, err.strerror)
        raise

    try:
        if canwrite:
            fcntl.flock(efile, fcntl.LOCK_EX)
    except IOError as err:
        result['error'] = "LOCK_EX on %s failed: %s" % (filename, err.strerror)
        raise

    return efile

def _write_exports(efile, exports, result):
    """ Write out exports entries """
    try:
        lastpath = None
        for exp in exports:
            path = exp[0]
            host = exp[1]
            opt = exp[2]

            if path != lastpath:
                lastpath = path
                if ' ' in path:
                    path = '"%s"' % path
                efile.write("%s" % (path))

            if len(opt) > 0:
                efile.write(" %s(%s)" % (host, opt))
            else:
                efile.write(" %s" % (host))
        efile.write("\n")
    except IOError as err:
        result['error'] = 'Write error: %s' % (err.strerror)
        raise

def match_export(exportlist, path, host):
    """ Check through exportlist for a matching entry """

    if exportlist is None or len(exportlist) < 1:
        return False
    found = False
    for exp in exportlist:
        if exp[0] == path and exp[1].lower() == host.lower():
            found = True
    return found

def filter_export(exportlist, path, host):
    """ Remove matching export from exportlist """

    if exportlist is None or len(exportlist) < 1:
        raise LookupError

    found = False
    newlist = []
    for exp in exportlist:
        if exp[0] == path and exp[1].lower() == host.lower():
            found = True
        else:
            newlist.append(exp)

    if not found:
        raise LookupError

    return newlist

def update_exports(result):
    """ Run exportfs to update the system export list """
    cmd = [_EXPORTFS, '-a']
    try:
        check_output(cmd, stderr=subprocess.STDOUT)
    except OSError as err:
        result['error'] = 'Error running %s: %s' % (cmd[0], err.strerror)
        raise
    except CalledProcessError as err:
        result['error'] = 'Error updating exports: %s' % (err.output)
        raise

def replace_export(path, clients, options, clear_all, result):
    """
        Do an inline replace/add of the given exports
        Removes any existing reference to (path,clients)
        If options is not None then add new entry
    """
    lines = 0
    try:
        outfile = tempfile.NamedTemporaryFile(dir=os.path.dirname(_EXPORTS),
                                              prefix=os.path.basename(_EXPORTS),
                                              delete=False, suffix=".tmp")
        tmppath = outfile.name
    except (OSError, IOError) as err:
        result['error'] = 'Error with tmpfile: %s' % (err.strerror)
        raise

    try:
        infile = _open_exports(False, _EXPORTS, result)
    except IOError:
        os.unlink(tmppath)
        raise

    try:
        for line in infile:
            if line == '' or line[0] == '#':
                outfile.write(line)
                lines += 1
            else:
                if clear_all:
                    continue
                exports = _parse_export(line)
                if match_export(exports, path, clients):
                    exports = filter_export(exports, path, clients)
                    if exports:
                        _write_exports(outfile, exports, result)
                        lines += 1
                else:
                    outfile.write(line)
                    lines += 1

        if not lines:
            outfile.write('# NFS exports managed by Ansible\n')

        if options is not None:
            exports = [(path, clients, options),]
            _write_exports(outfile, exports, result)

        outfile.close()
        infile.close()
        os.rename(tmppath, _EXPORTS)
    except (IOError, OSError) as err:
        if not result['error']:
            result['error'] = 'Error during replace: %s' % (err.strerror)
        os.unlink(tmppath)
        raise

def _option_compose(read_only, root_squash, all_squash, security, options):
    """ Compose an options string from the various parameters """
    optset = {}
    if read_only:
        optset['ro'] = 'ro'
    else:
        optset['rw'] = 'rw'
    if not root_squash:
        optset['no_root_squash'] = 'no_root_squash'
    if all_squash:
        optset['all_squash'] = 'all_squash'
    if security:
        optset['sec'] = security

    optstr = _print_options(optset)

    if options:
        if len(optstr) > 1:
            optstr = optstr + ','
        optstr = optstr + options

    return optstr

def run_module():
    """ Module code """
    # define the available arguments/parameters that a user can pass to
    # the module
    module_args = dict(
        name=dict(type='str', required=True),
        update=dict(type='bool', required=False, default=True),
        clear_all=dict(type='bool', required=False, default=False),
        action=dict(type='str', required=False),
        path=dict(type='str', required=False),
        clients=dict(type='str', required=False),
        read_only=dict(type='bool', required=False, default=True),
        root_squash=dict(type='bool', required=False, default=True),
        all_squash=dict(type='bool', required=False, default=False),
        security=dict(type='str', required=False),
        options=dict(type='str', required=False)
    )

    # seed the result dict in the object
    # we primarily care about changed and state
    # change is if this module effectively modified the target
    # state will include any data that you want your module to pass back
    # for consumption, for example, in a subsequent task
    result = dict(
        changed=False,
        name='',
        message='',
        error=None
    )

    # the AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module
    # supports check mode
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    # copy through the name parameter
    result['name'] = module.params['name']

    # if the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    if module.check_mode:
        return result

    path = module.params['path']
    host = module.params['clients']
    clear_all = module.params['clear_all']

    # do we need to add or remove anything from that list
    if module.params['action'] == 'add':
        result['message'] = 'Adding export'
        opt = _option_compose(module.params['read_only'],
                              module.params['root_squash'],
                              module.params['all_squash'],
                              module.params['security'],
                              module.params['options'])

        if not os.path.exists(path) or not os.path.isdir(path):
            module.fail_json(msg='Path does not exist or is not a directory',
                             **result)

        try:
            replace_export(path, host, opt, clear_all, result)
        except (IOError, OSError):
            module.fail_json(msg='Error adding export', **result)


    elif module.params['action'] == 'remove':
        try:
            replace_export(path, host, None, clear_all, result)
        except (IOError, OSError):
            module.fail_json(msg='Error adding export', **result)
    else:
        result['message'] = 'Bad action'
        module.fail_json(msg='Unknown action type specified', **result)

    # Optionally kick nfsd to reload the list
    if module.params['update']:
        try:
            update_exports(result)
        except (OSError, CalledProcessError):
            module.fail_json(msg='Error updating exports', **result)

    # during the execution of the module, if there is an exception or a
    # conditional state that effectively causes a failure, run
    # AnsibleModule.fail_json() to pass in the message and the result
    if module.params['name'] == 'fail me':
        module.fail_json(msg='You requested this to fail', **result)

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)

def main():
    """ entry point """
    run_module()

if __name__ == '__main__':
    main()

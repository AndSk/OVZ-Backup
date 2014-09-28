#!/usr/bin/python

import argparse
import uuid
import subprocess
import syslog
import sys

class BackupCmdError(Exception):
    def __init__(self, cmd, error):
        self.value = "Error: command \"{0}\" failed with error message \"{1}\"".format(cmd, error)
    def __str__(self):
        return repr(self.value)

class OVZBackup:
    def __init__(self, mail_to = [], debug = False, verbose = False):
        self.debug = debug
        self.verbose = verbose
        self.mail_to = mail_to

    def add_mail_recipient(self, address):
        self.mail_to.append(address)

    def _log_error(self, error):
        print >>sys.stderr, error
        syslog.syslog(syslog.LOG_ERR, error)

        for recipient in self.mail_to:
            call_cmd(self._send_mail_cmd(recipient, "ovz-backup failure"), input = error, verbose = self.verbose, debug = self.debug)
        
    def _send_mail_cmd(self, mail_to, subject):
        return ['mail', '-s', subject, mail_to]
        
    def _openvz_private_cmd(self, ctid):
        return ['vzlist', '-H', '-o', 'private', str(ctid)]

    def _openvz_snapshot_cmd(self, ctid, unique_id):
        return ['vzctl', 'snapshot', str(ctid), '--id', str(unique_id), '--skip-suspend', '--skip-config']

    def _openvz_snapshot_delete_cmd(self, ctid, unique_id):
        return ['vzctl', 'snapshot-delete', str(ctid), '--id', str(unique_id)]

    def _backup_cmd(self, file_to_back_up, backup_to):
        rsync = ['rsync']
        rsync_remote_args = []
        rsync_local_args = ['-a', '--delete', '--stats', '--inplace', '-v']
        nice = ['nice', '-n', '19']
        ionice = ['ionice', '-c', '3']
        rsync_remote_cmd = nice + ionice + rsync + rsync_remote_args
        
        rsync_local_cmd = rsync_remote_cmd + \
                          ["--rsync-path='{0}'".format(" ".join(rsync_remote_cmd))] + \
                          rsync_local_args + \
                          [file_to_back_up, backup_to]
        
        return rsync_local_cmd

    def _backup_snapshot(self, ctid, backup_path):
        ve_private = call_cmd(self._openvz_private_cmd(ctid)).rstrip()

        backup_snapshot_path = "{0}/snapshot/{1}".format(backup_path, ctid)
        backup_conf_path = "{0}/conf/{1}".format(backup_path, ctid)
        
        conf_path = "/etc/vz/conf/{0}.*".format(ctid)
        snapshot_path = "{0}/root.hdd/*".format(ve_private)

        #Create a unique ID for the snapshot
        unique_id = uuid.uuid4()

        try:
            #Take a snapshot
            call_cmd(self._openvz_snapshot_cmd(ctid, unique_id),
                     verbose = self.verbose,
                     debug = self.debug)

            #Backup conf files using rsync
            call_cmd(self._backup_cmd(conf_path, backup_conf_path),
                     shell = True,
                     verbose = self.verbose,
                     debug = self.debug)

            #Backup snapshot files using rsync
            call_cmd(self._backup_cmd(snapshot_path, backup_snapshot_path),
                     shell = True,
                     verbose = self.verbose,
                     debug = self.debug)
        finally:
            #Remove the snapshot
            call_cmd(self._openvz_snapshot_delete_cmd(ctid, unique_id),
                     verbose = self.verbose,
                     debug = self.debug)

    def backup(self, ctids, path):
        failed_ctids = []
        successful_ctids = []

        #Back up each container and remember if it failed or not.
        for ctid in ctids:
            try:
                self._backup_snapshot(ctid, path)
                successful_ctids.append(ctid)
            except OSError as e:
                #A call command could not be executed. Log this and try the next container.
                self._log_error(str(e))
                failed_ctids.append(ctid)
            except BackupCmdError as e:
                #A backup command failed. Log this and try the next container.
                self._log_error(str(e))
                failed_ctids.append(ctid)

        return (failed_ctids, successful_ctids)

def call_cmd(cmd, input = None, shell = False, verbose = False, debug = False):
    cmd_str = " ".join(cmd)

    if shell:
        cmd = cmd_str
        
    if debug:
        print("Call: '{0}' with input {1}".format(cmd_str, input))
        return ""
    else:
        p = subprocess.Popen(cmd, shell = shell,
                             stdin = subprocess.PIPE,
                             stdout = subprocess.PIPE,
                             stderr = subprocess.PIPE )

        (stdout,stderr) = p.communicate(input)

        if p.returncode != 0:
            raise BackupCmdError(cmd_str, stderr)
        
        if verbose:
            print stdout
        
        return stdout



def main():
    syslog.openlog('ovz-backup')

    parser = argparse.ArgumentParser(description=
                                     "Backs up OpenVZ ploop containers with rsync. "
                                     "An optional list of container IDs to back up can be provided. "
                                     "If no list is given all containers will be backed up. "
                                     "If the exclude flag is set then all containers except those provided in the list will be backed up.")
    
    parser.add_argument('-i', '--ctids', action='store', nargs='+', type=int,
                        help="List of CTID\'s to either back up or exclude.")

    parser.add_argument('-e', '--exclude', default=False, action='store_true',
                        help="Back up all containers except those provided in the CTID list.")

    parser.add_argument('-d', '--debug', default=False, action='store_true',
                        help="Print out all backup commands instead of executing them. No changes will be made.")

    parser.add_argument('-v', '--verbose', default=False, action='store_true', help="Be verbose.")

    parser.add_argument('path', help="Path to where backups shall be stored.")

    parser.add_argument('-t', '--mailto', action='append', default=[],
                        help="Mail address to send error messages to.")

    args = parser.parse_args()

    #Get a list of all OpenVZ containers
    all_ctids_raw = call_cmd(['vzlist', '-a', '-Hoctid'])

    #Remove whitespaces
    all_ctids = [int(s) for s in all_ctids_raw.split() if s.isdigit()]

    #If the exclude flag is set then back up all containers except those in the list provided by the user.
    #If the exclude flag is set but no list of containers was provided, then give an error and exit.
    #If the exclude flag is not set and no list of containers was provided, back up all containers.
    #If the exclude flag is not set and a list of containers was provided, back up all containers in that list.
    #And just in case, only back up containers that exists.

    if args.exclude == True:
        if args.ctids != None:
            to_back_up = list(set(all_ctids) - set(args.ctids))
        else:
            sys.exit("Error: empty list of CTIDs provided when in exclude mode")
    else:
        if args.ctids != None:
            to_back_up = list(set(all_ctids) & set(args.ctids))
        else:
            to_back_up = all_ctids

    ovz_backup = OVZBackup(mail_to = args.mailto, debug = args.debug, verbose = args.verbose)

    (failed_ctids, successful_ctids) = ovz_backup.backup(to_back_up, args.path)

    if args.verbose:
        print("Successful backups:")
        for ctid in successful_ctids:
            print(ctid)

        print("Failed backups:")
        for ctid in failed_ctids:
                print(ctid)
 
    if len(failed_ctids) > 0:
        sys.exit("{0} backups failed".format(len(failed_ctids)))

if __name__ == "__main__":
    main()

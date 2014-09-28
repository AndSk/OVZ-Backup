# OVZ-Backup

OVZ-Backup is a small python script that creates ploop snapshots of OpenVZ containers and backs them up with rsync. It can either back up all OpenVZ containers, or be given a list of container IDs that it should either back up or exclude. All errors from OpenVZ or rsync are logged with syslog. OVZ-Backup can also take a list of users or email addresses that should be notified when errors occur.

## Usage

```
ovz-backup [OPTIONS] path
```

path

	Path to where backups shall be stored.

### Options

-h, --help

	Show help message

-i CTIDS [CTIDS ...], --ctids CTIDS [CTIDS ...]

List of CTID's to either back up or exclude.

-e, --exclude

	Back up all containers except those provided in the CTID list.

-d, --debug

	Print out all backup commands instead of executing them. No changes will be made.

-v, --verbose

	Be verbose.

-t MAILTO, --mailto MAILTO

	Mail address to send error messages to.

## Examples

Only back up the containers 101, 102, and 103.
```
ovz-backup.py -i 101 102 103 -v -- backupuser@backup.example.com:/path/to/backup/folder/
```
Back up all containers except 101 and send error messages to user@example.com and admin@example.com.
```
ovz-backup.py -t user@example.com -t admin@example.com -i 101 -e -v -- backupuser@backup.example.com:/path/to/backup/folder/
```
Back up all containers and send error messages to root. Do a test run without creating snapshots or writing any data.
```
ovz-backup.py -t root -d -v -- backupuser@backup.example.com:/path/to/backup/folder/
```

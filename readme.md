Pkg-Tracker
===============

## pkg_tracker.py

A utility that tracks the history of packages installed on Debian systems using apt.
This provides a quick and easy way to find what packages are installed where,
of what versions, and when they were installed/updraded/deleted. The utility itself mostly
executes mysql queries, and does not do any of the data-gathering itself, but that is easy
enough and documented here-in.

## Features

* Tracks package names, versions, architectures, status and source
* Ingests data formatted from dpkg -l output
* Uses mysql-like wildcards for fuzzy searching
* Same utility to search and ingest data
* Simple Mysql schema that can work with existing Asset tracking databases

## Usage
```
usage: pkg_tracker.py [-h] [--fqdn FQDN] [--feed [FEED]] [--ver VER]
                      [--pkg PKG] [--arch ARCH] [--status STATUS] [--src SRC]
                      [--noheader [NOHEADER]] [--debug [DEBUG]]
                      [--remove [REMOVE]]
                      {get,add,update}

Find, Add or Update debian package info about systems

positional arguments:

  {get,add,update}

optional arguments:
  -h, --help            show this help message and exit
  --fqdn FQDN           fqdn of host
  --feed [FEED]         takes in piped dpkg output to update the db
  --ver VER             version of package
  --pkg PKG             name of package
  --arch ARCH           architecture of package
  --status STATUS       status of package
  --src SRC             package manager source
  --noheader [NOHEADER] do not print header for results
  --debug [DEBUG]       print db actions
  --remove [REMOVE]     specify date a pkg is removed from host. 
                        Set to 1 when running update to set "removed" to "NOW".
                        Defaults to "%" for searches to work and be ignored by update/add.
```

The command takes an action word (get, add or update) and several options to describe the action to take.
Most common use will be get and add. Get will retrieve a list of package data matching the criteria provided.
Add will add packages for a given host, while update updates existing info on an existing package/host.
The command treats a host/package/version tuple as a unique key to facilitate version tracking.
A new version will add a new entry unless the update action is specifically used.
Using --remove will mark the package as removed when using update, or will allow searching on removed packages
(ie: historical packages or versions no longer present on the host).
The --feed option is specifically used by a script that loads/updates all packages/hosts in bulk.
It only works with add, and expects the output of a dpkg -l command piped directly into it and should add and update hosts/packages/versions appropriately.

## Requirements

* Python
* Debian system using APT (dpkg)
* Mysql (including at a minimum, a table with host.fqdn and host.id, example schema provided)

## Examples

### Searching

To search, run the utility with "get". Use % as a wildcard character.

```
# pkg_tracker.py get --pkg openssl
fqdn	status	arch	source	installed	modified	removed	pkg_version	pkg_name
host1.fqdn 15:36:59	2018-03-06 15:36:59	None	1.0.2l-1~bpo8+1	openssl
host2.fqdn 15:37:00	2018-03-06 15:37:00	None	1.0.2l-1~bpo8+1	openssl
host3.fqdn 15:37:02	2018-03-06 15:37:02	None	1.0.2l-1~bpo8+1	openssl
host4.fqdn 15:37:03	2018-03-06 15:37:03	None	1.0.2l-1~bpo8+1	openssl
...
```

Add attributes to filter more things

```
# pkg_tracker.py get --pkg libperl% --fqdn %some%
fqdn	status	arch	source	installed	modified	removed	pkg_version	pkg_name
some.host1 15:36:43	2018-03-06 15:36:43	None	0.003-1	libperl4-corelibs-perl
some.other 15:36:43	2018-03-06 12:11:26	None	5.20.2-3+deb8u9	libperl5.20
host.some  15:36:43	2018-02-17 09:43:42	None	5.15.4-2+deb8u3	libperl5.15
some.some  15:36:43	2018-02-16 11:26:31	None	5.12.0-6+deb8u0	libperl5.12
```

(todo: fix brokenpipe when piping output)

### Adding Entries

To Add, similar to get, specify the attributes for the package. This must include fqdn, pkg, ver.
You should also include arch, amd64, status and remove, though they have sane defaults.
arch defaults to amd64, status to ii and src to apt. Others default to values that will not work correctly and should throw errors.

```bash
pkg_tracker.py add --fqdn some.host.fqdn --pkg some_package-name --ver version-tag --status ii --arch amd64
```

(todo: add better error handling)

### Ingesting Data

To bulk-load data into the database, the output of dpkg -l for each host should be collected and piped into 

```bash
pkg_tracker.py add --fqdn $FQDN --feed
```

An example that runs all hosts in an inventory system that are marked "active":

```bash
for i in `sudo mysql -u inventory_user inventory -e 'select fqdn from hosts where inventory_component_type = "system" AND status="active" \G ' | grep fqdn | cut -f2 -d:` ; do
  echo $i
  ping -c2 -t2 -w3 -q $i > /dev/null
  if [[ $? -gt 0 ]] ; then
    echo "No Ping! Skipping"
    continue
  fi
  ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes $i 'dpkg -l  ' | python ./pkg_tracker.py add --fqdn=$i --feed
done
```

This can be put into a self-contained script and run from cron for history tracking.

If direct ssh access is not allowed, the dpkg command can be run from a server that can reach all systems, its output collected into files named by fqdn, then that data transmitted back to the host with pkg_tracker for bulk loading. Ex:

```bash
sudo mysql -u inventory_user inventory -e 'select fqdn from hosts where inventory_component_type="system" and status != "decommissioned"' > hostlist.out
scp hostlist.out some.other.system:~/tmp_pkgtracker_out/

ssh some.other.system
cd tmp_pkgtracker_out
for i in `cat hostlist.out ` ; do
  echo $i
  ping -c1 -w3 -q $i > /dev/null
  if [[ $? -gt 0 ]] ; then
    echo \"No Ping! Skipping\"
    continue
    echo .
  fi
  ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes $i "sudo dpkg -l"> ${i}.pkglist
done
rsync -a *pkglist first.system:~/results.pkgtracker/
exit

for i in `cat hostlist.cmdb ` ; do
  if [[ -f results.pkgtracker/${i}.pkglist ]] ; then
    echo $i
    cat results.pkgtracker/${i}.pkglist | pkg_tracker.py add --fqdn=${i} --feed
  fi
done
```

### Updating By Hand

This should not be used much as the bulk feed methods above should pick up on changes when run. Much the same as how search and other functions work, update is similar.

```bash
pkg_tracker.py update --fqdn some.host.fqdn --pkg some_package-name --ver version-tag --status ii 
```

Required fields are fqdn, pkg, and ver. It will only update status, removed, and arch as specified. If the version changes, use update to set the old version to removed (ie: --remove 1), then add a new package entry. (todo: simplify this to auto-remove/add for version changes)

### Removing Versions or Packages

Use update, as described above, setting --remove 1 and status xx

```bash
pkg_tracker.py update --fqdn some.host.fqdn --pkg some_package-name --ver version-tag --status xx --remove 1 
```


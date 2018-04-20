#!/usr/bin/python

import getopt
import sys
import mysql.connector
from mysql.connector import errorcode
import argparse
import time
import re

db_config = {
  'user': 'pkgtracker',
  'password': 'usearealpasswordhere',
  'host': 'yourinventorydbhost',
  'database': 'inventorydb',
  'buffered': True,
}

## define a few query templates

# add a new package
add_pkg_name = ("INSERT IGNORE INTO pkg_enum "
                "(pkg_name) "
                "VALUES (%s)" )
# add a new version string
add_pkg_version = ("INSERT IGNORE INTO pkg_version_enum "
                   "(pkg_version) "
                   "VALUES (%s) " )

# add a package+version reference to a host
add_host_package = ("INSERT IGNORE INTO packages "
                    "(host_id,pkg_id,pkg_version_id,status,arch,source,modified) "
                    "VALUES (%s,%s,%s,%s,%s,%s,NOW()) ")

# Update a package assigned to a host. Updates only status, modified timestam and removed timestamp
update_host_package = """UPDATE packages
                        SET status=%s,removed=%s,modified=%s
                        WHERE host_id=%s AND pkg_id=%s AND pkg_version_id=%s"""

# Update this to match your inventory table id and fqdn fields. id is used for joins, fqdn for string searches.
get_host_id = ("SELECT id FROM device WHERE fqdn LIKE %s")

get_pkg_id = ("SELECT pkg_id FROM pkg_enum WHERE pkg_name LIKE %s")

get_ver_id = ("SELECT pkg_version_id FROM pkg_version_enum WHERE pkg_version LIKE %s")

# more things to update in here, search/replace b.fqdn, b.id, "device as b" with your schema stuff as above
get_packages = ("SELECT b.fqdn,a.status,a.arch,a.source,a.installed,a.modified,a.removed,d.pkg_version,c.pkg_name FROM packages"
                " AS a LEFT JOIN device AS b ON a.host_id=b.id LEFT JOIN pkg_enum AS c ON a.pkg_id=c.pkg_id"
                " LEFT JOIN pkg_version_enum AS d ON a.pkg_version_id=d.pkg_version_id WHERE b.fqdn LIKE %s"
                " AND c.pkg_name LIKE %s AND d.pkg_version LIKE %s AND a.status LIKE %s AND a.arch LIKE %s AND a.source LIKE %s AND a.removed LIKE %s")

try:
  cnx = mysql.connector.connect(**db_config)
except mysql.connector.Error as err:
  if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
    print("Something is wrong with your user name or password")
  elif err.errno == errorcode.ER_BAD_DB_ERROR:
    print("Database does not exist")
  else:
    print "Error code:", err.errno        # error number
    print "SQLSTATE value:", err.sqlstate # SQLSTATE value
    print "Error message:", err.msg       # error message
    print "Error:", err                  # errno, sqlstate, msg values
    s = str(err)
    print "Error:", s                   # errno, sqlstate, msg values

# returns pkg info for a set of criteria
def get_package_list(cnx, fqdn, pkg_name, pkg_ver, status, arch, src, removed):
  cursor=cnx.cursor()
  cursor.execute(get_packages,(fqdn,pkg_name,pkg_ver,status,arch,src,removed))
  pkglist=[]
  for (row) in cursor:
    pkglist.append(row)
  return(pkglist)

# adds a package and version to a host, takes fqdn, package name, version string, status code, arch string
def add_pkg_to_host (cnx,fqdn,pkg,ver,status,arch,src,removed):
  pkg_id=0
  ver_id=0
  host_id=0
  pkg_id=get_pkg_from_name(cnx,pkg)
  ver_id=get_ver_from_name(cnx,ver)
  host_id=get_host_from_fqdn(cnx,fqdn)
  if removed == 1:
    removed = time.strftime('%Y-%m-%d %H:%M:%S')
  elif removed == '%':
    removed = '0000-00-00 00:00:00'
  cursor=cnx.cursor()
  cursor.execute(add_host_package,(host_id,pkg_id,ver_id,status,arch,src))
  cnx.commit()
  cursor.close()
  return

# updates a package reference on a host. Only fields for updating are status, removed, arch. 
#    Changing version or package should be a new package table entry
def update_package(cnx, fqdn,status,arch,removed,pkg,ver):
  pkg_id=0
  ver_id=0
  host_id=0
  pkg_id=get_pkg_from_name(cnx,pkg)
  ver_id=get_ver_from_name(cnx,ver)
  host_id=get_host_from_fqdn(cnx,fqdn)
  hosts=get_package_list(cnx,fqdn,pkg,ver,"%","%","%","%")
  
  cursor=cnx.cursor()
  
  modified=time.strftime('%Y-%m-%d %H:%M:%S')
  if removed>0:
    removed=modified
    status="xx"
  else:
    removed="0000-00-00 00:00:00"
  if args.debug:
    print "Updating stuff: UPDATE packages SET status=%s,removed=%s,modified=%s WHERE host_id=%s AND pkg_id=%s AND pkg_version_id=%s " % (status,removed,modified,host_id,pkg_id,ver_id)
  cursor.execute(update_host_package,(status,removed,modified,host_id,pkg_id,ver_id))
  cnx.commit()
  return

## returns package id from enum table, inserts if needed
def get_pkg_from_name (cnx, pkg_name):
  pkg_id=0
  cursor=cnx.cursor()
  cursor.execute(get_pkg_id,(pkg_name,))
  if cursor.rowcount > 0:
    for (id,) in cursor:
      pkg_id=id
  else:
    cursor.execute(add_pkg_name,(pkg_name,))
    pkg_id=cursor.lastrowid
    cnx.commit
  cursor.close()
  return pkg_id

## returns version id from enum table, inserts if needed
def get_ver_from_name (cnx, pkg):
  ver_id=0
  cursor=cnx.cursor()
  cursor.execute(get_ver_id,(pkg,))
  if cursor.rowcount > 0:
    for (id,) in cursor:
      ver_id=id
  else:
    cursor.execute(add_pkg_version,(pkg,))
    ver_id=cursor.lastrowid
    cnx.commit
  cursor.close()
  return ver_id

## returns host id from device table
def get_host_from_fqdn (cnx, fqdn):
  host_id=0
  cursor=cnx.cursor()
  cursor.execute(get_host_id,(fqdn,))
  if cursor.rowcount > 0:
    for (id,) in cursor:
      host_id=id
  else:
    raise Exception("Error! host with fqdn %s does not exist!" % fqdn)
  cursor.close()
  return host_id

argp=argparse.ArgumentParser(description='Find, Add or Update debian package info about systems')
argp.add_argument('action', choices=['get','add','update'])
argp.add_argument('--fqdn', default="%", help='fqdn of host')
argp.add_argument('--feed', nargs='?', const=True, help='takes in piped dpkg output to update the db')
argp.add_argument('--ver', default="%", help='version of package')
argp.add_argument('--pkg', default="%", help='name of package')
argp.add_argument('--arch', default="amd64", help='architecture of package')
argp.add_argument('--status', default="ii", help='status of package')
argp.add_argument('--src', default="apt", help='package manager source')
argp.add_argument('--noheader', nargs='?', const=True, help='do not print header for results')
argp.add_argument('--debug', nargs='?', const=True, help='print db actions')
argp.add_argument('--remove', nargs='?', const=True, default="%", help="specify date a pkg is removed from host. Set to 1 when updating to set to NOW. Defaults to %(default)s for searches to work.")
args=argp.parse_args()

if args.action=="get":
  pkgs=get_package_list(cnx, args.fqdn,args.pkg,args.ver,args.status,args.arch,args.src,args.remove)
  if not args.noheader:
    print "\t".join(("fqdn","status","arch","source","installed","modified","removed","pkg_version","pkg_name"))
  for row in pkgs:
    print "\t".join(map(str, row)) 

if args.action=="add":
  if args.feed:
    lc=0
    hostdpkg_list=[]
    # get the list of all packages from the db that it shows on this host including removed (will update status if removed)
    # returns an array of rows of: fqdn,status,arch,source,installed,modified,removed,pkg_version,pkg_name
    dbdpkg_list = get_package_list(cnx, args.fqdn,"%","%","%","%","%","%")
    for line in sys.stdin:
      lc=lc+1
      if lc > 5:
        dpkgin = re.split('\s+',line)[0:3]
        # save a slice of the array for reverse-compare with the db
        # dpkgin=(status,pkg,ver,description elements) 
        hostdpkg_list.append(dpkgin[0:3])
        if args.debug:
          print ",".join(dpkgin)
        for dbpkg in dbdpkg_list:
          # If package name and version match
          if dbpkg[8] == dpkgin[1] and dbpkg[7] == dpkgin[2]:
            if args.debug:
              print "Existing package found %s ver %s match  %s %s" % (dbpkg[8], dbpkg[7], dpkgin[1], dpkgin[2])
            # compare status. Update if not the same, continue if it matches, set update flag and 
            if dbpkg[1] != dpkgin[0]:
              if args.debug:
                print "Status mismatch, updating package  %s to status %s" % (dbpkg[1], dpkgin[0])
              update_package(cnx,args.fqdn,dpkgin[0],args.arch,0,dpkgin[1],dpkgin[2])
            break
        else:
          #no match in the db, add the pkg
          if args.debug:
            print "No existing match found, adding: %s ver %s status %s" % (dpkgin[1], dpkgin[2],dpkgin[0])
          add_pkg_to_host(cnx,args.fqdn,dpkgin[1],dpkgin[2],dpkgin[0],args.arch,args.src,'0000-00-00 00:00:00')
    ## Now go through whats in the DB, skip ones already removed, remove any from the DB not found on the host
    for dbpkg in dbdpkg_list:
      if dbpkg[1] == 'xx':
        continue
      if args.debug:
        print "Checking package %s ver %s status %s" % (dbpkg[8], dbpkg[7], dbpkg[1])
      ## check that all the db packages are still here, remove if not
      for hostpkg in hostdpkg_list:
        if dbpkg[8] == hostpkg[1] and dbpkg[7] == hostpkg[2]:
          if args.debug:
            print "Pkg found: %s ver %s matching %s and %s" % (dbpkg[8], dbpkg[7], hostpkg[1], hostpkg[2])
          break
      else:
        if args.debug:
          print "setting old package to removed: %s ver %s" % (dbpkg[8], dbpkg[7])
        update_package(cnx,args.fqdn,dbpkg[1],args.arch,"1",dbpkg[8],dbpkg[7])
  else:
    if args.remove=='%':
      remove="0000-00-00 00:00:00"
    else:
      remove=args.remove
    add_pkg_to_host(cnx,args.fqdn,args.pkg,args.ver,args.status,args.arch,args.src,args.remove)

cnx.close()


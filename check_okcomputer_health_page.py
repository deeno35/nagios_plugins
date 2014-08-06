#!/usr/bin/env python
######
###
# Description: Poll a health check URL.  It should return JSON like this:
# {
#     "check_name1" : {
#             "message" : "string result",
#             "success" : true
#                    },
#     "check_name2" : {
#             "message" : "any string result",
#             "success" : false
#                    }
# }
#
# Description: Walk healthpages reported by the okcomputer ruby gem and return
#    status codes to nagios based on ok/non-ok states.  Use of the oklcomputer
#    gem will enforce the json formatting
#
#    okcomputer ruby gem github:
#    https://github.com/sportngin/okcomputer
#
# Author: d_k_nguyen@yahoo.com
# Date: 08/05/2014
#
# Notes: there is a weakness to using okcomputer in that it returns status
#    as a boolean (true / false) so there is no way to enforce returning
#    warning vs critical states.  For the purpose of this script, we will
#    be returning a crit for every check where success != 'true'


import getopt
import os
import re
import sys
import pycurl
import cStringIO
import simplejson as json

def usage():
    print ("USAGE: check_okl_health_page -H <hostname> [-u <URL>] [-p <port>] ",
        "[-S] [-e <check_to_exclude>]")
    print "-H hostname (default: imp.newokl.com)"
    print "-p port (default: 80)"
    print "-S check via ssl"
    print "-u URL (default: /health_checks)\n\n"
    sys.exit(3)

def parse_args():
    """
    Returns a dict of the args as it's easier to work with than a list of
    tuples.
    """
    return_dict = {"hostname" : "localhost",
                    "port" : 80,
                    "ssl" : False,
                    "url" : "/health_checks",
                    "excludeList" : ['stub']}
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hH:p:Su:e:")
    except getopt.GetoptError:
        usage()
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
        elif opt in ("-H", "--hostname"):
            return_dict["hostname"] = str(arg)
        elif opt in ("-p", "--port"):
            return_dict["port"] = int(arg)
        elif opt in ("-S", "--ssl"):
            return_dict["ssl"] = True
        elif opt in ("-u", "--url"):
            return_dict["url"] = str(arg)
        elif opt in ("-e", "--exclude"):
            return_dict["excludeList"].append(str(arg))

    # Arg enforcement
    #if "http" not in return_dict["url"]:
        #print "ERROR: " + return_dict["url"] + " is not a proper URL"
        #print "Example URL: https://imp.newokl.com/health_check"
        #usage()

    return return_dict

class Check:
    """
    Based on oklcompany ruby gem health check page output.  Checks will
    have a name, success, and message.

    success == true means the check passes.
    """
    name = ""
    message = ""
    success = False

    def __init__(self,name, message, success):
        self.set_name(name)
        self.set_message(message)
        self.set_success(success)

    def __str__ (self):
        return "%s : {message: %s, success: %s}" % (self.get_name(),
                                                    self.get_message(),
                                                    self.get_success())
    def get_name(self):
        return self.name

    def get_message(self):
        return self.message

    def get_success(self):
        return self.success

    def set_name(self, value):
        self.name = value

    def set_message(self, value):
        self.message = value

    def set_success(self, value):
        self.success = value



if __name__ == '__main__':
    badList = []
    args = parse_args()
    if args["ssl"]:
        url = "https://"
    else:
        url = "http://"
    url += "%s:%d%s" % (args["hostname"], args["port"], args["url"])

    buffer = cStringIO.StringIO()
    c = pycurl.Curl()
    c.setopt(c.URL, url)
    c.setopt(c.WRITEFUNCTION, buffer.write)
    try:
        c.perform()
    except pycurl.error, e:
        print "UNKOWN: problem pycurling " + url
        sys.exit(3)
    # Validate response
    if c.getinfo(c.HTTP_CODE) != 200:
        print "UNKNOWN: %s returned a non 200 status code" % (url)
        sys.exit(3)
    try:
        jsonResponse = json.loads(buffer.getvalue())
    except ValueError:
        print "UNKNOWN: %s returned a non-json formatted string: %s" % (
                url,buffer.getvalue())
        sys.exit(3)
    buffer.close()

    # Find bad values
    #DEBUG#print json.dumps(json_response, indent=4 * ' ')

    for checkName,valueDict in jsonResponse.items():
        if valueDict["success"] == False:
            badList.append(Check(checkName, valueDict["message"], valueDict["success"]))

    if not badList:
        print "OK: All checks pass"
        sys.exit(0)
    else:
        msg = "CRITICAL: The following checks are failing"
        for check in badList:
            msg += ", " + str(check)

        print msg
        sys.exit(2)


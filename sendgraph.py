#!/usr/bin/env python
"""
Adapted from: 
https://gist.github.com/bkjones/1902478

This takes a recipient email address and a graphite URL and sends a 
POST to <graphite host>/dashboard/email with a body that looks like
this: 

    sender=user%40example.com&recipients=user2%40example.com&
    subject=foo&message=bar&graph_params=%7B%22
    target%22%3A%22target%3DdrawAsInfinite(metric.path.in.graphite)
    %22%2C%22from%22%3A%22-2hours%22%2C%22until%22%3A%22now%22%2C%22
    width%22%3A600%2C%22height%22%3A250%7D

...which will cause the graphite installation to send an email.

command definition would look like this:
# 'notify-svcgraph-by-email' command definition
define command{
        command_name    notify-svcgraph-by-email
        command_line    $USER5$/sendgraph.py -u "http://$USER6$" 
        --interval 6hours --from_email "from_address@example.com"
        }

service definition would look like this:
define service{
    use                     prod_template
    service_description     s_dn_test
    check_command           check_graphite2!30min!-z ok
    host_name               localhost
    _WARN                   1
    _CRIT                   5
    _GRAPHITE_METRIC        maxSeries(stats.gauges.count.*)
    action_url              https://myrunbook/link
}

Updates:
- use icinga environment variables where possible
- don't bother sending notification event
- html email formatting
- decouple graphite metric from the graphite URL.  This is because visually
we will often times want something different than what the check is doing
(ie 6 hour graph in the email, but generally we don't want the check to be
looking over 6hrs)
- alert thresholds printed on graph

Author: David Nguyen
"""
import requests
import logging
import sys
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
from optparse import OptionParser
import os

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
LOGGER = logging.getLogger(os.path.basename(__file__))
graphite_metric = os.getenv('ICINGA__SERVICEGRAPHITE_METRIC', None)
warn_threshold = os.getenv('ICINGA__SERVICEWARN', None)
crit_threshold = os.getenv('ICINGA__SERVICECRIT', None)
contact_email = os.getenv('ICINGA_CONTACTEMAIL', None)
notification_type = os.getenv('ICINGA_NOTIFICATIONTYPE', None)
service_state = os.getenv('ICINGA_SERVICESTATE', None)
host_alias = os.getenv('ICINGA_HOSTALIAS', None)
host_address = os.getenv('ICINGA_HOSTADDRESS', None)
service_description = os.getenv('ICINGA_SERVICEDESC', None)
date_time = os.getenv('ICINGA_LONGDATETIME', None)
action_url = os.getenv('ICINGA_SERVICEACTIONURL', None)
service_output = os.getenv('ICINGA_SERVICEOUTPUT', None)
service_duration = os.getenv('ICINGA_SERVICEDURATION', None)

def send_graph_email(graph, subject, sender, receivers, body=None):
    """
    Builds an email with the attached graph.

    :param body: Text portion of the alert notification email. 
    :param graph: Assumed to be a PNG, currently.
    :param subject: Email subject line
    :param sender: an email address
    :param receivers: list of email addresses to send to.
    :return:
    """
    LOGGER.debug("body: %s  subject: %s  sender: %s  receivers: %s" % (
        body, subject, sender, receivers))
    if body is None:
        body = '\n'

    if graph is not None:
        #Append graph to bottom of the email body
        body += '<BR><BR><img src="cid:graph">'
        imgpart = MIMEImage(graph, 'png')
        imgpart.add_header('Content-ID', '<graph>')
        imgpart.add_header(
            'Content-Disposition', 'inline', filename='graph.png')

    msg = MIMEMultipart('related')
    msg.attach(MIMEText(body, 'html'))

    if graph is not None:
        msg.attach(imgpart)

    msg['to'] = ', '.join(receivers)
    msg['from'] = sender
    msg['subject'] = subject
    s = smtplib.SMTP()
    try:
        s.connect()
        s.sendmail(sender, receivers, msg.as_string())
        s.close()
    except Exception as out:
        logging.error("Sending mail failed: %s" % out)

def get_highlight_color(notification_type, service_state):
    # default
    color = "fuchsia" 

    if notification_type == "ACKNOWLEDGEMENT":
        color = "cyan"
    elif notification_type == "CUSTOM":
        color = "greenyellow"
    elif service_state == "CRITICAL":
        color = "lightcoral"
    elif service_state == "WARNING":
        color = "yellow"
    elif service_state == "OK":
        color = "springgreen"
    elif service_state == "UNKNOWN":
        color = "grey"

    return color

def generate_email_body(bgcolor):
    body = ("{date_time}<BR><BR>"
            "<TABLE border='0'>"
            "<TR bgcolor='{bgcolor}'><TD><B>Service State:</B></TD>"
            "<TD><B>{service_state}</B></TD></TR>"
            "<TR><TD>Notification Type:</TD><TD>{notification_type}</TD></TR>"
            "<TR><TD>Service:</TD><TD>{service_description}</TD></TR>"
            "<TR><TD>Host:</TD><TD>{host_alias}</TD></TR>"
            "<TR><TD>Address:</TD><TD>{host_address}</TD></TR>"
            "<TR><TD>Runbook:</TD><TD>"
            "<A HREF='{action_url}'>{action_url}</A></TD></TR>"
            "<TR><TD>Problem Duration:</TD><TD>{service_duration}</TD></TR>"
            "<TR><TD></TD><TD></TD></TR>"
            "<TR><TD>Check Output:</TD><TD>{service_output}</TD></TR>"
            "</TABLE>".format(date_time=date_time, bgcolor=bgcolor,
                notification_type=notification_type,
                service_state=service_state,
                service_description=service_description,
                host_alias=host_alias, host_address=host_address,
                action_url=action_url, service_duration=service_duration,
                service_output=service_output))
    return body

def get_graph(options):
    """
    We need to handle the case where no graphite graph is being used in the
    check.  Return None in those cases
    Returns: either response.content (png of graphite graph) or None
    """
    if graphite_metric is not None:
        graph_url = ("{base_url}/render?lineMode=connected&from=-{interval}&"
                     "width={width}&target={graphite_metric}"
                     "&bgcolor=FFFFFF&fgcolor=000000".format(
                        base_url=options.base_url,
                        interval=options.interval,
                        width=options.width,
                        graphite_metric=graphite_metric))
        if warn_threshold is not None:
            graph_url += "&target=threshold({0},'warn = {0}','yellow')".format(
                warn_threshold)
        if crit_threshold is not None:
            graph_url += "&target=threshold({0}, 'crit = {0}','red')".format(
                crit_threshold)

        LOGGER.debug('graph url is %s' % graph_url)
        result = requests.get(graph_url)
        LOGGER.debug("Response headers for graph request: %s", result.headers)
        graph = result.content
    else:
        graph = None

    return graph

def get_options():
    parser = OptionParser()
    parser.add_option('-u', '--url',
                      action='store',
                      dest='base_url',
                      help='Graphite Base URL http://localhost:14770')
    parser.add_option('-i', '--interval',
                      action='store',
                      dest='interval',
                      default='6hours',
                      help='Graph Interval to display')
    parser.add_option('-W', '--width',
                      action='store',
                      dest='width',
                      default='800',
                      help='Graph width')
    parser.add_option('-f', '--from_email',
                      action='store',
                      dest='from_email',
                      help='From email address')
    options, args = parser.parse_args()
    return options

def main():
    options = get_options()
    bgcolor = get_highlight_color(notification_type, service_state)
    body = generate_email_body(bgcolor)

    # Can uncomment this for debugging - print all env vars out to see what 
    # icinga is doing...
    #
    # for key in os.environ.keys():
    #     body += "<BR><BR>{0}: {1}<BR>".format(key, os.environ[key])

    subject = ("{notification_type} {service_state} "
               "{host_alias}/{service_description}".format(
                notification_type=notification_type,
                service_state=service_state, host_alias=host_alias,
                service_description=service_description))

    graph = get_graph(options)

    send_graph_email(
        graph, subject, options.from_email, contact_email.split(' '), body)
    LOGGER.debug("Mail sent")


if __name__ == '__main__':
    main()

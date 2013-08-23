#!/usr/bin/env python
#
# Copyright 2012, Rackspace US, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import glob
import lockfile
import multiprocessing
import os
import signal
import ConfigParser
from glance.common import config
from glance.openstack.common import log
# We import notify_kombu and filesystem for the CONF options only.
from glance.notifier import notify_kombu
from glance.store import filesystem
from kombu import BrokerConnection
from kombu import Exchange
from kombu import Queue
from os import system
from oslo.config import cfg
from socket import gethostname
from sys import exit as sysexit
from time import sleep


LOG = log.getLogger(__name__)

conf_file_opts = [
    cfg.StrOpt('api_nodes', default=None),
    cfg.StrOpt('rsync_user', default='glance'),
    cfg.StrOpt('lock_file', default='/var/lock/glance-image-sync/glance-image-sync'),
    cfg.StrOpt('glance_api_conf', default='/etc/glance/glance-api.conf')
]

CONF = cfg.CONF
CONF.register_opts(conf_file_opts)
CONF.register_cli_opt(cfg.BoolOpt('daemon', default=False))


def _build_config_dict():
    # TODO (mattt): find a better way to read these configuration options
    # from CONF.glance_api_conf
    glance_cfg = {}
    section = 'DEFAULT'
    config = ConfigParser.RawConfigParser()

    if config.read(CONF.glance_api_conf):
        if config.get(section, 'notifier_strategy') == 'rabbit':
            tmp_api_nodes = CONF.api_nodes
            glance_cfg['api_nodes'] = tmp_api_nodes.replace(' ', '').split(',')
            glance_cfg['rsync_user'] = CONF.rsync_user

            glance_cfg['host'] = config.get(section, 'rabbit_host')
            glance_cfg['port'] = config.get(section, 'rabbit_port')
            glance_cfg['use_ssl'] = config.get(section, 'rabbit_use_ssl')
            glance_cfg['userid'] = config.get(section, 'rabbit_userid')
            glance_cfg['password'] = config.get(section, 'rabbit_password')
            glance_cfg['virtual_host'] = config.get(section,
                                                    'rabbit_virtual_host')
            option = 'rabbit_notification_exchange'
            glance_cfg['exchange'] = config.get(section, option)
            glance_cfg['topic'] = config.get(section,
                                             'rabbit_notification_topic')
            glance_cfg['datadir'] = config.get(section,
                                               'filesystem_store_datadir')

            return glance_cfg
        else:
            return None
    else:
        return None


def _connect(glance_cfg):
    # We use BrokerConnection rather than Connection as RHEL 6 has an ancient
    # version of kombu library.
    conn = BrokerConnection(hostname=glance_cfg['host'],
                            port=glance_cfg['port'],
                            userid=glance_cfg['userid'],
                            password=glance_cfg['password'],
                            virtual_host=glance_cfg['virtual_host'])
    exchange = Exchange(glance_cfg['exchange'],
                        type='topic',
                        durable=False,
                        channel=conn.channel())

    return conn, exchange


def _declare_queue(glance_cfg, routing_key, conn, exchange):
    queue = Queue(name=routing_key,
                  routing_key=routing_key,
                  exchange=exchange,
                  channel=conn.channel(),
                  durable=False)
    queue.declare()

    return queue


def _shorten_hostname(node):
    # If hostname is an FQDN, split it up and return the short name. Some
    # systems may return FQDN on socket.gethostname(), so we choose one
    # and run w/ that.
    if '.' in node:
        return node.split('.')[0]
    else:
        return node


def _duplicate_notifications(glance_cfg):
    conn, exchange = _connect(glance_cfg)
    routing_key = '%s.info' % glance_cfg['topic']
    notification_queue = _declare_queue(glance_cfg,
                                        routing_key,
                                        conn,
                                        exchange)

    while True:
        msg = notification_queue.get()

        if msg:
            # Skip over non-glance notifications.
            if msg.payload['event_type'] not in ('image.update', 'image.delete'):
                continue

            for node in glance_cfg['api_nodes']:
                routing_key = ('glance_image_sync.%s.info' %
                               _shorten_hostname(node))
                node_queue = _declare_queue(glance_cfg,
                                            routing_key,
                                            conn,
                                            exchange)

                msg_new = exchange.Message(msg.body,
                                           content_type='application/json')
                exchange.publish(msg_new, routing_key)

            LOG.info("%s %s %s" % (msg.payload['event_type'],
                                   msg.payload['payload']['id'],
                                   msg.payload['publisher_id']))
            msg.ack()
        elif not CONF.daemon:
            break

        sleep(1)

    conn.close()


def _sync_images(glance_cfg):
    conn, exchange = _connect(glance_cfg)
    hostname = gethostname()

    routing_key = 'glance_image_sync.%s.info' % _shorten_hostname(hostname)
    queue = _declare_queue(glance_cfg, routing_key, conn, exchange)

    while True:
        msg = queue.get()

        if msg:
            image_filename = "%s/%s" % (glance_cfg['datadir'],
                                        msg.payload['payload']['id'])

            # An image create generates a create and update notification, so we
            # just pass over the create notification and use the update one
            # instead.
            # Also, we don't send the update notification to the node which
            # processed the request (publisher_id) since that node will already
            # have the image; we do send deletes to all nodes though since the
            # node which receives the delete request may not have the completed
            # image yet.
            if (msg.payload['event_type'] == 'image.update' and
                    msg.payload['publisher_id'] != hostname):
                print 'Update detected on %s ...' % (image_filename)
                system("rsync -a -e 'ssh -o StrictHostKeyChecking=no' "
                       "%s@%s:%s %s" % (glance_cfg['rsync_user'],
                                        msg.payload['publisher_id'],
                                        image_filename, image_filename))
                msg.ack()
            elif msg.payload['event_type'] == 'image.delete':
                print 'Delete detected on %s ...' % (image_filename)
                # Don't delete file if it's still being copied (we're looking
                # for the temporary file as it's being copied by rsync here).
                image_glob = '%s/.*%s*' % (glance_cfg['datadir'],
                                           msg.payload['payload']['id'])
                if not glob.glob(image_glob):
                    system('rm %s' % (image_filename))
                    msg.ack()
            else:
                msg.ack()
        elif not CONF.daemon:
            break

        sleep(1)

    conn.close()


def main():
    def cleanup(signum, frame):
        p1.terminate()
        p2.terminate()

    config.parse_args()

    log.setup('rcb')
    glance_cfg = _build_config_dict()

    if not glance_cfg:
        sysexit(1)

    if CONF.daemon:
        # If we run as a daemon, we assume we're running via start-stop-daemon
        # or similar
        p1 = multiprocessing.Process(target=_duplicate_notifications,
                                     args=(glance_cfg,))
        p2 = multiprocessing.Process(target=_sync_images,
                                     args=(glance_cfg,))
        p1.start()
        p2.start()

        signal.signal(signal.SIGTERM, cleanup)
        signal.signal(signal.SIGINT, cleanup)

        p1.join()
        p2.join()
    else:
        # Lock AFTER arguments have been parsed, otherwise we'll end up with
        # stale lock files.
        lock = lockfile.FileLock(CONF.lock_file)
        if lock.is_locked():
            sysexit(1)
    
        with lock:
            _sync_images(glance_cfg)
            _duplicate_notifications(glance_cfg)

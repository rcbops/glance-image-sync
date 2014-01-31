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

import argparse
import ConfigParser
import glob
import logging
import os
import socket
import sys

import lockfile

import kombu


IMAGE_SYNC_CONFIG = '/etc/glance/glance-image-sync.conf'
GLANCE_API_CONFIG = '/etc/glance/glance-api.conf'
RSYNC_COMMAND = (
    "rsync -a -e 'ssh -o StrictHostKeyChecking=no'"
    " %(user)s@%(host)s:%(file)s %(file)s"
)


def _read_api_nodes_config():
    image_sync_cfg = {}
    section = 'DEFAULT'
    default_log = '/var/log/glance/glance-image-sync.log'
    default_lock = '/var/run/glance-image-sync'
    config = ConfigParser.RawConfigParser({'rsync_user': 'glance',
                                           'log_file': default_log,
                                           'lock_file': default_lock})

    if config.read(IMAGE_SYNC_CONFIG):
        tmp_api_nodes = config.get(section, 'api_nodes')
        image_sync_cfg['rsync_user'] = config.get(section, 'rsync_user')
        image_sync_cfg['log_file'] = config.get(section, 'log_file')
        image_sync_cfg['lock_file'] = config.get(section, 'lock_file')
        image_sync_cfg['api_nodes'] = tmp_api_nodes.replace(' ', '').split(',')

        return image_sync_cfg
    else:
        return None


def _read_glance_api_config():
    glance_api_cfg = {}
    section = 'DEFAULT'
    config = ConfigParser.RawConfigParser()

    if config.read(GLANCE_API_CONFIG):
        if config.get(section, 'notifier_strategy') == 'rabbit':
            glance_api_cfg['host'] = config.get(section, 'rabbit_host')
            glance_api_cfg['port'] = config.get(section, 'rabbit_port')
            glance_api_cfg['use_ssl'] = config.get(section, 'rabbit_use_ssl')
            glance_api_cfg['userid'] = config.get(section, 'rabbit_userid')
            glance_api_cfg['password'] = config.get(section,
                                                    'rabbit_password')
            glance_api_cfg['virtual_host'] = config.get(section,
                                                        'rabbit_virtual_host')
            option = 'rabbit_notification_exchange'
            glance_api_cfg['exchange'] = config.get(section, option)
            glance_api_cfg['topic'] = config.get(section,
                                                 'rabbit_notification_topic')
            glance_api_cfg['datadir'] = config.get(section,
                                                   'filesystem_store_datadir')

            return glance_api_cfg
        else:
            return None
    else:
        return None


def _connect(glance_api_cfg):
    """Create the connection the AMQP.

    We use BrokerConnection rather than Connection as RHEL 6 has an ancient
    version of kombu library.
    """

    conn = kombu.BrokerConnection(
        hostname=glance_api_cfg['host'],
        port=glance_api_cfg['port'],
        userid=glance_api_cfg['userid'],
        password=glance_api_cfg['password'],
        virtual_host=glance_api_cfg['virtual_host']
    )
    exchange = kombu.Exchange(
        glance_api_cfg['exchange'],
        type='topic',
        durable=False,
        channel=conn.channel()
    )

    return conn, exchange


def _declare_queue(routing_key, conn, exchange):
    """Declare the queue that we are working with."""

    queue = kombu.Queue(
        name=routing_key,
        routing_key=routing_key,
        exchange=exchange,
        channel=conn.channel(),
        durable=False
    )
    queue.declare()

    return queue


def _shorten_hostname(node):
    """If hostname is an FQDN, split it up and return the short name.

    Some systems may return FQDN on socket.gethostname(), so we choose one
    and run w/ that.
    """

    if '.' in node:
        return node.split('.')[0]
    else:
        return node


def _message_publish(message, exchange, routing_key):
    """Publish Messages back to AMQP."""

    msg_new = exchange.Message(
        message, content_type='application/json'
    )
    exchange.publish(msg_new, routing_key)


def _duplicate_notifications(glance_api_cfg, image_sync_cfg, conn, exchange):
    routing_key = '%s.info' % glance_api_cfg['topic']
    notification_queue = _declare_queue(
        routing_key, conn, exchange
    )

    while True:
        msg = notification_queue.get()

        if msg is None:
            break

        # Skip over non-glance notifications.
        if msg.payload['event_type'] not in ('image.update', 'image.delete'):
            continue

        for node in image_sync_cfg['api_nodes']:
            routing_key = 'glance_image_sync.%s.info' % _shorten_hostname(node)
            _message_publish(msg.body, exchange, routing_key)

        reporter(
            "%s %s %s" % (
                msg.payload['event_type'],
                msg.payload['payload']['id'],
                msg.payload['publisher_id']
            )
        )

        msg.ack()


def _sync_images(glance_api_cfg, image_sync_cfg, conn, exchange):
    """Sync Images and ACK for the message as found in RabbitMQ."""

    hostname = socket.gethostname()
    routing_key = 'glance_image_sync.%s.info' % _shorten_hostname(hostname)
    sync_queue = _declare_queue(
        routing_key, conn, exchange
    )

    while True:
        msg = sync_queue.get()
        if msg is None:
            break

        image_filename = "%s/%s" % (
            glance_api_cfg['datadir'], msg.payload['payload']['id']
        )

        # An image create generates a create and update notification, so we
        # just pass over the create notification and use the update one
        # instead.
        # Also, we don't send the update notification to the node which
        # processed the request (publisher_id) since that node will already
        # have the image; we do send deletes to all nodes though since the
        # node which receives the delete request may not have the completed
        # image yet.

        system_process = [
            msg.payload['event_type'] == 'image.update',
            msg.payload['publisher_id'] != hostname
        ]

        if all(system_process):
            reporter('Update detected on "%s"' % image_filename)
            process_args = {
                'user': image_sync_cfg['rsync_user'],
                'host': msg.payload['publisher_id'],
                'file': image_filename
            }
            os.system(RSYNC_COMMAND % process_args)
            _message_publish(msg.body, exchange, 'notifications.info')

        elif msg.payload['event_type'] == 'image.delete':
            reporter('Delete detected on %s ...' % image_filename)
            # Don't delete file if it's still being copied (we're looking
            # for the temporary file as it's being copied by rsync here).
            image_glob = '%s/.*%s*' % (
                glance_api_cfg['datadir'], msg.payload['payload']['id']
            )
            if not glob.glob(image_glob):
                os.remove(image_filename)
                _message_publish(msg.body, exchange, 'notifications.info')
        else:
            _message_publish(msg.body, exchange, 'notifications.info')


def reporter(message):
    """Report Any Messages that need reporting."""

    print(message)
    logging.info(message)


def _arg_parser():
    """Setup argument Parsing."""

    parser = argparse.ArgumentParser(
        usage='%(prog)s',
        description='Rackspace Openstack, Glance Image Sync Application',
        epilog='Glance Image Sync Licensed "Apache 2.0"')

    subpar = parser.add_subparsers()

    dup = subpar.add_parser(
        'duplicate-notifications',
        help='process duplicate notifications.'
    )
    dup.set_defaults(method='duplicate_notifications')

    syn = subpar.add_parser(
        'sync-images',
        help='Sync Images between Controller Nodes.'
    )
    syn.set_defaults(method='sync_images')

    bth = subpar.add_parser(
        'both',
        help='Perform all operations.'
    )
    bth.set_defaults(method='both')

    return parser


def main():
    """Run Main Application."""

    parser = _arg_parser()
    if len(sys.argv) < 2:
        raise SystemExit(parser.print_help())
    else:
        cmd = vars(parser.parse_args())

        glance_api_cfg = _read_glance_api_config()
        image_sync_cfg = _read_api_nodes_config()

        if glance_api_cfg and image_sync_cfg:
            logging.basicConfig(filename=image_sync_cfg['log_file'],
                                format='%(asctime)s %(message)s',
                                level=logging.INFO)
            conn, exchange = _connect(glance_api_cfg)

            lock = lockfile.FileLock(image_sync_cfg["lock_file"])

            if lock.is_locked():
                raise SystemExit('Lock file was already locked.')
            else:

                with lock:
                    if cmd['method'] == 'duplicate-notifications':
                        _duplicate_notifications(
                            glance_api_cfg, image_sync_cfg, conn, exchange
                        )
                    elif cmd['method'] == 'sync-images':
                        _sync_images(
                            glance_api_cfg, image_sync_cfg, conn, exchange
                        )
                    elif cmd['method'] == 'both':
                        _duplicate_notifications(
                            glance_api_cfg, image_sync_cfg, conn, exchange
                        )
                        _sync_images(
                            glance_api_cfg, image_sync_cfg, conn, exchange
                        )

                    conn.close()
        else:
            raise SystemExit(
                'Application was not able to parse the glance-image-sync'
                ' config, the glance API config or both.'
            )

if __name__ == '__main__':
    main()

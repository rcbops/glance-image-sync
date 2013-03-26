import os
import socket
import sys
import ConfigParser
from kombu import Connection
from kombu import Exchange
from kombu import Queue

API_NODES = ['ubuntu-ha1', 'ubuntu-ha2']

def _read_config():
    rabbit_cfg = {}
    section = 'DEFAULT'
    config = ConfigParser.RawConfigParser()
    config.read('/etc/glance/glance-api.conf')

    rabbit_cfg['host'] = config.get(section, 'rabbit_host')
    rabbit_cfg['port'] = config.get(section, 'rabbit_port')
    rabbit_cfg['use_ssl'] = config.get(section, 'rabbit_use_ssl')
    rabbit_cfg['userid'] = config.get(section, 'rabbit_userid')
    rabbit_cfg['password'] = config.get(section, 'rabbit_password')
    rabbit_cfg['virtual_host'] = config.get(section, 'rabbit_virtual_host')
    rabbit_cfg['exchange'] = config.get(section, 'rabbit_notification_exchange')
    rabbit_cfg['topic'] = config.get(section, 'rabbit_notification_topic')

    return rabbit_cfg


def _connect(rabbit_cfg):
    conn = Connection('amqp://%s:%s@%s:%s//' % (rabbit_cfg['userid'],
                                                rabbit_cfg['password'],
                                                rabbit_cfg['host'],
                                                rabbit_cfg['port']))
    exchange = Exchange(rabbit_cfg['exchange'],
                        type='topic',
                        durable=False,
                        channel=conn.channel())

    return conn, exchange


def _declare_queue(rabbit_cfg, routing_key, conn, exchange):
    queue = Queue(name=routing_key,
                  routing_key=routing_key,
                  exchange=exchange,
                  channel=conn.channel(),
                  durable=False)
    queue.declare()

    return queue


def duplicate_notifications(rabbit_cfg, conn, exchange):
    routing_key = '%s.info' % rabbit_cfg['topic']
    notification_queue = _declare_queue(rabbit_cfg, routing_key, conn, exchange)

    while True:
        msg = notification_queue.get()

        if msg == None:
            break

        for node in API_NODES:
            routing_key = '%s.%s.info' % (rabbit_cfg['topic'], node)
            node_queue = _declare_queue(rabbit_cfg, routing_key, conn, exchange)

            if msg.payload['publisher_id'] != node:
                msg_new = exchange.Message(msg.body,
                                           content_type='application/json')
                exchange.publish(msg_new, routing_key)

        msg.ack()

    conn.close()


def sync_images(rabbit_cfg, conn, exchange):
    hostname = socket.gethostname()

    routing_key = '%s.%s.info' % (rabbit_cfg['topic'], hostname)
    queue = _declare_queue(rabbit_cfg, routing_key, conn, exchange)

    while True:
        msg = queue.get()

        if msg == None:
            break

        if (msg.payload['payload']['location'] is not None and
            'file://' in msg.payload['payload']['location']):
            file = msg.payload['payload']['location'].replace('file://','')
            if msg.payload['event_type'] == 'image.update':
                print 'Update detected on %s ...' % (file)
                os.system("rsync -a -e 'ssh -o StrictHostKeyChecking=no' "
                          "root@%s:%s %s" % (msg.payload['publisher_id'],
                                             file, file))
            elif msg.payload['event_type'] == 'image.delete':
                print 'Delete detected on %s ...' % (file)
                os.system('rm %s' % (file))

        msg.ack()

    conn.close()


def main(args):
    if len(args) == 2:
        cmd = args[1]
    else:
        sys.exit(1)

    if cmd in ('duplicate', 'sync'):
        rabbit_cfg = _read_config()
        conn, exchange = _connect(rabbit_cfg)
    else:
        sys.exit(1)

    if cmd == 'duplicate':
        duplicate_notifications(rabbit_cfg, conn, exchange)
    elif cmd == 'sync':
        sync_images(rabbit_cfg, conn, exchange)


if __name__ == '__main__':
    main(sys.argv)

glance-image-sync
-----------------

glance-image-sync is a tool to help sync glance images between two or more glance-api nodes using _default_store_ of _file_ (no shared storage).  The tool is intended to be run via cron on each glance-api node and requires glance-api to be configured with:

    notifier_strategy = rabbit

When run, glance-image-sync will pull messages from the _info_ queue defined by _rabbit_notification_topic_ (default _glance_notifications_) and then duplicate these messages into queues for each individual glance-api node.  The list of glance-api nodes is stored in _/etc/glance/glance-image-sync.conf_.  Once messages have been duplicated, glance-image-sync will pull messages from the node's individual queue.  If a message contains an _image.update_ event_type, the image will be copied via rsync from the glance-api node defined by the message's _publisher_id_.  If the message contains an _image.delete_ event_type, the image will simply be removed from the node's local filesystem.

Your /etc/glance/glance-image-sync.conf should look like:

    [DEFAULT]
    api_nodes = node1,node2,node3,...

API nodes can be specified in /etc/glance/glance-image-sync.conf using a short name or FQDN; both will work as we check for FQDN and then shorten it. However, the glance kombu notifier uses _socket.gethostname()_ for _publisher_id_, so you will need to ensure that nodes can be accessed by name using short name and FQDN since socket.gethostname() may return short name or FQDN depending on how the system was configured.

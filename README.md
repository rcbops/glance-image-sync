glance-image-sync
-----------------

glance-image-sync is a tool to help sync glance images between two or more glance-api nodes using default_store of file (no shared storage).  The tool is intended to be run via cron on each glance-api node and requires glance-api to be configured with:

    notifier_strategy = rabbit

When run, glance-image-sync will pull messages from the info queue defined by rabbit_notification_topic (default glance_notifications) and then duplicate these messages into queues for each individual glance-api node.  The list of glance-api nodes is stored in /etc/glance/glance-image-sync.conf.  Once messages have been duplicated, glance-image-sync will pull messages from the node's individual queue.  If a message contains an image.update event_type, the image will be copied via rsync from the glance-api node defined by the message's publisher_id.  If the message contains an image.delete event_type, it will simply be removed from the local filesystem.

Your /etc/glance/glance-image-sync.conf should look like:

    [DEFAULT]
    api_nodes = node1,node2,node3,...

API nodes can be specified in /etc/glance/glance-image-sync.conf using a short name or FQDN; both will work as we check for FQDN and then shorten it. However, the glance kombu notifier uses socket.gethostname() for publisher_id, so you will need to ensure that nodes can be accessed by name using short name and FQDN since socket.gethostname() may return short name or FQDN depending on how the system was configured.

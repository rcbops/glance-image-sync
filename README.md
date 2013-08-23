glance-image-sync
-----------------

glance-image-sync is a tool to help sync glance images between two or more glance-api nodes using _default_store_ of _file_ (no shared storage).  The tool is intended to be run via cron on each glance-api node and requires glance-api to be configured with:

    notifier_strategy = rabbit

When run, glance-image-sync will pull messages from the _info_ queue defined by _rabbit_notification_topic_ (default _glance_notifications_) and then duplicate these messages into queues for each individual glance-api node.  The list of glance-api nodes is stored in /etc/glance/glance-image-sync.conf.  Once messages have been duplicated, glance-image-sync will pull messages from the node's individual queue.  If a message contains an _image.update_ event_type, the image will be copied via rsync from the glance-api node defined by the message's _publisher_id_.  If the message contains an _image.delete_ event_type, the image will simply be removed from the node's local filesystem.

Your /etc/glance/glance-image-sync.conf should look like:

    [DEFAULT]
    api_nodes = node1,node2,node3,...
    rsync_user = someone
    log_file = /var/log/glance/glance-image-sync.log
    verbose = True

API nodes can be specified in /etc/glance/glance-image-sync.conf using a short name or FQDN; both will work as we check for FQDN and then shorten it. However, the glance kombu notifier uses _socket.gethostname()_ for _publisher_id_, so you will need to ensure that nodes can be accessed by name using short name and FQDN since socket.gethostname() may return short name or FQDN depending on how the system was configured.  Additionally, you can optionally specify the ssh user rsync uses to retrieve images.  If left unspecified, this will default to the _glance_ user.

When running glance-image-sync, you will need to pass the tool one of the following three arguments:

* duplicate-notifications
* sync-images
* both

_duplicate-notifications_ only connects to the _rabbit_notification_topic_ queue and duplicates messages into queues for each glance-api node defined in /etc/glance/glance-image-sync.conf. _sync-images_ only connects to the node's individual queue and then downloads or deletes images depending on event_type.  _both_ is simply a wrapper to both _duplicate-notifications_ and _sync-images_.  Typically, you would cron the job on each glance-api node as follows:

    */5 * * * * /path/to/glance-image-sync.py both

The frequency of the cronjob will need to be adjusted per environment.

Your /etc/glance/glance-image-sync.conf should look like:

    [DEFAULT]
    api_nodes = node1,node2,node3,...

API nodes can be specified in /etc/glance/glance-image-sync.conf using a short name or FQDN; both will work as we check for FQDN and then shorten it. However, the glance kombu notifier uses socket.gethostname() for publisher_id, so you will need to ensure that nodes can be accessed by name using short name and FQDN since socket.gethostname() may return short name or FQDN depending on how the system was configured.

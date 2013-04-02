Your /etc/glance/glance-image-sync should.conf look like:

    [DEFAULT]
    api_nodes = node1,node2,node3,...

If you find that a node is not picking up messages correctly, ensure that the node name in /etc/glance/glance-image-sync.conf matches what is returned by socket.gethostname().

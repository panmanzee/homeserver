#!/bin/bash
# workhub only: the zabbix server container connects from the docker bridge, allow it
sed -i "s|^Server=.*|Server=100.108.65.118,172.16.0.0/12|" /etc/zabbix/zabbix_agent2.conf
systemctl restart zabbix-agent2
systemctl is-active zabbix-agent2

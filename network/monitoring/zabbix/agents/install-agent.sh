#!/bin/bash
# install zabbix agent 2 (run as root on the target)
# usage: install-agent.sh <hostname> <debian13|debian12|ubuntu24.04>
set -e
HN="$1"; OSV="$2"
SRV=100.108.65.118
cd /tmp
curl -fsSLO "https://repo.zabbix.com/zabbix/7.0/$(echo $OSV | sed 's/[0-9.]*$//')/pool/main/z/zabbix-release/zabbix-release_latest_7.0+${OSV}_all.deb"
dpkg -i zabbix-release_latest_7.0+${OSV}_all.deb
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq zabbix-agent2
C=/etc/zabbix/zabbix_agent2.conf
sed -i "s/^Server=.*/Server=$SRV/; s/^ServerActive=.*/ServerActive=$SRV/; s/^Hostname=.*/Hostname=$HN/" $C
# docker plugin needs the socket (containers only)
if [ -S /var/run/docker.sock ]; then usermod -aG docker zabbix; fi
systemctl enable zabbix-agent2
systemctl restart zabbix-agent2
sleep 2
systemctl is-active zabbix-agent2

! FRR for the Proxmox host, eBGP to the AWS VGW over the two tunnels
frr defaults traditional
hostname pve-home
log syslog informational
!
ip prefix-list HOME-OUT seq 10 permit 10.10.0.0/16
! the zones are only /24s, so the /16 summary needs a local route to be announced
ip route 10.10.0.0/16 Null0
! no bfd here: the AWS VGW does not speak BFD (plain BGP keepalives instead)
ip prefix-list AWS-IN seq 10 permit 10.50.0.0/16 le 24
!
route-map TO-AWS permit 10
 match ip address prefix-list HOME-OUT
!
route-map FROM-AWS permit 10
 match ip address prefix-list AWS-IN
!
router bgp ${home_asn}
 bgp router-id ${router_id}
 no bgp ebgp-requires-policy
@@NEIGHBORS@@
 address-family ipv4 unicast
  network 10.10.0.0/16
@@AF@@
 exit-address-family
!
line vty
!

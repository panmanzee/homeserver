resource "aws_vpn_gateway" "vgw" {
  vpc_id          = aws_vpc.dr.id
  amazon_side_asn = var.amazon_side_asn
  tags            = { Name = "homelab-dr-vgw" }
}

resource "aws_customer_gateway" "home" {
  bgp_asn    = var.homelab_bgp_asn
  ip_address = var.customer_gateway_ip
  type       = "ipsec.1"
  tags       = { Name = "homelab-cgw" }
}

resource "aws_vpn_gateway_route_propagation" "private" {
  count          = var.create_route_propagation ? 1 : 0
  vpn_gateway_id = aws_vpn_gateway.vgw.id
  route_table_id = aws_route_table.private.id
}

resource "aws_vpn_connection" "home" {
  count                = var.create_vpn_connection ? 1 : 0
  vpn_gateway_id       = aws_vpn_gateway.vgw.id
  customer_gateway_id  = aws_customer_gateway.home.id
  type                 = "ipsec.1"
  static_routes_only   = false # BGP
  tunnel1_ike_versions = ["ikev2"]
  tunnel2_ike_versions = ["ikev2"]

  tags = { Name = "homelab-vpn" }
}

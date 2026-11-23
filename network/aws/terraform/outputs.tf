output "vpc_id" {
  value = aws_vpc.dr.id
}

output "vgw_id" {
  value = aws_vpn_gateway.vgw.id
}

output "amazon_side_asn" {
  value = var.amazon_side_asn
}

output "homelab_asn" {
  value = var.homelab_bgp_asn
}

output "tunnels" {
  description = "Per-tunnel data for the homelab render script"
  sensitive   = true
  value = var.create_vpn_connection ? [
    {
      name        = "aws1"
      aws_outside = aws_vpn_connection.home[0].tunnel1_address
      cgw_inside  = aws_vpn_connection.home[0].tunnel1_cgw_inside_address
      aws_inside  = aws_vpn_connection.home[0].tunnel1_vgw_inside_address
      inside_cidr = aws_vpn_connection.home[0].tunnel1_inside_cidr
      psk         = aws_vpn_connection.home[0].tunnel1_preshared_key
    },
    {
      name        = "aws2"
      aws_outside = aws_vpn_connection.home[0].tunnel2_address
      cgw_inside  = aws_vpn_connection.home[0].tunnel2_cgw_inside_address
      aws_inside  = aws_vpn_connection.home[0].tunnel2_vgw_inside_address
      inside_cidr = aws_vpn_connection.home[0].tunnel2_inside_cidr
      psk         = aws_vpn_connection.home[0].tunnel2_preshared_key
    },
  ] : []
}

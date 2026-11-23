resource "aws_security_group" "dr" {
  name        = "dr-instance"
  description = "DR box: ssh only from homelab MGMT over the VPN"
  vpc_id      = aws_vpc.dr.id

  ingress {
    description = "ssh from MGMT"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.mgmt_cidr]
  }

  ingress {
    description = "ping from homelab"
    from_port   = -1
    to_port     = -1
    protocol    = "icmp"
    cidr_blocks = var.homelab_cidrs
  }

  egress {
    description = "to homelab and VPC only"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = concat(var.homelab_cidrs, [var.vpc_cidr])
  }

  tags = { Name = "dr-instance-sg" }
}

resource "aws_network_acl" "private" {
  vpc_id     = aws_vpc.dr.id
  subnet_ids = aws_subnet.private[*].id
  tags       = { Name = "dr-private-nacl" }
}

# inbound: homelab ranges, plus ephemeral ports for return traffic
resource "aws_network_acl_rule" "in_homelab" {
  count          = length(var.homelab_cidrs)
  network_acl_id = aws_network_acl.private.id
  rule_number    = 100 + count.index
  egress         = false
  protocol       = "-1"
  rule_action    = "allow"
  cidr_block     = var.homelab_cidrs[count.index]
}

resource "aws_network_acl_rule" "in_ephemeral_vpc" {
  network_acl_id = aws_network_acl.private.id
  rule_number    = 200
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = var.vpc_cidr
  from_port      = 1024
  to_port        = 65535
}

resource "aws_network_acl_rule" "out_homelab" {
  count          = length(var.homelab_cidrs)
  network_acl_id = aws_network_acl.private.id
  rule_number    = 100 + count.index
  egress         = true
  protocol       = "-1"
  rule_action    = "allow"
  cidr_block     = var.homelab_cidrs[count.index]
}

resource "aws_network_acl_rule" "out_vpc" {
  network_acl_id = aws_network_acl.private.id
  rule_number    = 200
  egress         = true
  protocol       = "-1"
  rule_action    = "allow"
  cidr_block     = var.vpc_cidr
}

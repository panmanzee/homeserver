data "aws_ami" "al2023" {
  count       = var.enable_dr_instance && var.dr_ami_id == "" ? 1 : 0
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023*-x86_64"]
  }
}

resource "aws_instance" "dr" {
  count                  = var.enable_dr_instance ? 1 : 0
  ami                    = var.dr_ami_id != "" ? var.dr_ami_id : data.aws_ami.al2023[0].id
  instance_type          = var.dr_instance_type
  subnet_id              = aws_subnet.private[0].id
  vpc_security_group_ids = [aws_security_group.dr.id]

  tags = { Name = "homelab-dr-box" }
}

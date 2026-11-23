variable "region" {
  type    = string
  default = "ap-southeast-1"
}

variable "use_localstack" {
  description = "Point the provider at LocalStack with dummy credentials"
  type        = bool
  default     = false
}

variable "localstack_endpoint" {
  type    = string
  default = "http://localhost:4567"
}

variable "vpc_cidr" {
  type    = string
  default = "10.50.0.0/16"
}

variable "azs" {
  type    = list(string)
  default = ["ap-southeast-1a", "ap-southeast-1b"]
}

variable "public_subnets" {
  type    = list(string)
  default = ["10.50.1.0/24", "10.50.2.0/24"]
}

variable "private_subnets" {
  type    = list(string)
  default = ["10.50.11.0/24", "10.50.12.0/24"]
}

variable "enable_nat" {
  description = "NAT gateway costs money, keep false unless needed"
  type        = bool
  default     = false
}

variable "homelab_cidrs" {
  description = "Home zones allowed over the VPN (MGMT, SERVERS, DMZ)"
  type        = list(string)
  default     = ["10.10.0.0/16"]
}

variable "mgmt_cidr" {
  type    = string
  default = "10.10.10.0/24"
}

variable "homelab_bgp_asn" {
  type    = number
  default = 65010
}

variable "amazon_side_asn" {
  type    = number
  default = 64512
}

variable "customer_gateway_ip" {
  description = "Public IP of the home router/Proxmox. Dynamic, so set it each time."
  type        = string
  default     = "203.0.113.10" # TEST-NET-3 placeholder
}

variable "create_vpn_connection" {
  description = "Set false to skip the VPN connection (LocalStack cannot do it)"
  type        = bool
  default     = true
}

variable "create_route_propagation" {
  description = "Set false only on LocalStack (EnableVgwRoutePropagation returns 501)"
  type        = bool
  default     = true
}

variable "enable_dr_instance" {
  type    = bool
  default = false
}

variable "dr_instance_type" {
  type    = string
  default = "t3.micro"
}

variable "dr_ami_id" {
  description = "AMI for the DR box. Empty = latest Amazon Linux 2023 lookup"
  type        = string
  default     = ""
}

variable "create_budget" {
  type    = bool
  default = true
}

variable "budget_email" {
  type    = string
  default = "you@example.com"
}

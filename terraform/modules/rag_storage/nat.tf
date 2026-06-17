# Look up the latest fck-nat Amazon Linux 2023 AMI dynamically
data "aws_ami" "fck_nat_ami" {
  count       = var.is_local_test ? 0 : 1
  most_recent = true
  owners      = ["568608671756"] # Official fck-nat owner

  filter {
    name   = "name"
    values = ["fck-nat-al2023-hvm-1.4.0-20260531-arm64-ebs"]
  }
}

module "fck_nat" {
  count   = var.is_local_test ? 0 : 1
  source  = "RaJiska/fck-nat/aws"
  version = "1.4.0"

  name      = "${var.resource_prefix}-fck-nat"
  vpc_id    = module.vpc[0].vpc_id
  subnet_id = module.vpc[0].public_subnets[0]

  # Pass the dynamically looked-up modern AL2023 AMI ID
  ami_id = data.aws_ami.fck_nat_ami[0].id

  # Enable high-availability mode (uses ASG to keep the NAT instance running)
  ha_mode = true

  instance_type = "t4g.nano"

  tags = local.merged_tags
}

# Native Terraform route to forward private egress traffic to the static ENI of fck-nat
resource "aws_route" "private_nat_route" {
  count                  = var.is_local_test ? 0 : length(module.vpc[0].private_route_table_ids)
  route_table_id         = module.vpc[0].private_route_table_ids[count.index]
  destination_cidr_block = "0.0.0.0/0"
  network_interface_id   = module.fck_nat[0].eni_id
}

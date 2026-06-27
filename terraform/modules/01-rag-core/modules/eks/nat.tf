module "fck_nat" {
  count   = var.create_nat_instance ? 1 : 0
  source  = "RaJiska/fck-nat/aws"
  version = "1.4.0"

  name      = "${var.resource_prefix}-fck-nat"
  vpc_id    = module.vpc.vpc_id
  subnet_id = module.vpc.public_subnets[0]

  ha_mode = true

  instance_type = "t4g.nano"

  tags = var.tags
}

resource "aws_route" "private_nat_route" {
  count                  = var.create_nat_instance ? length(module.vpc.private_route_table_ids) : 0
  route_table_id         = module.vpc.private_route_table_ids[count.index]
  destination_cidr_block = "0.0.0.0/0"
  network_interface_id   = module.fck_nat[0].eni_id
}

resource "aws_iam_role_policy_attachment" "fck_nat_ssm" {
  count      = var.create_nat_instance ? 1 : 0
  role       = module.fck_nat[0].role_name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

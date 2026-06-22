resource "aws_ebs_volume" "qdrant" {
  availability_zone = data.aws_availability_zones.available.names[0]
  size              = 150
  type              = "gp3"

  tags = merge(
    var.tags,
    {
      Name = "${var.resource_prefix}-qdrant-data"
    }
  )
}

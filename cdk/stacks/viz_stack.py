import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct

DOCKER_COMPOSE_YML = """version: '3'
services:
  db:
    image: postgres:15
    restart: always
    environment:
      POSTGRES_DB: superset
      POSTGRES_USER: superset
      POSTGRES_PASSWORD: superset
    volumes:
      - postgres_data:/var/lib/postgresql/data

  superset:
    image: apache/superset:latest
    restart: always
    depends_on:
      - db
    ports:
      - "8088:8088"
    environment:
      SUPERSET_SECRET_KEY: "medallion_superset_secret_key_2024"
      DATABASE_URL: "postgresql+psycopg2://superset:superset@db:5432/superset"
    volumes:
      - superset_home:/app/superset_home

volumes:
  postgres_data:
  superset_home:
"""

USER_DATA = f"""#!/bin/bash
set -e

# Install Docker
yum update -y
yum install -y docker
systemctl enable docker
systemctl start docker

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-linux-x86_64" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Write docker-compose.yml
mkdir -p /opt/medallion
cat > /opt/medallion/docker-compose.yml << 'COMPOSE_EOF'
{DOCKER_COMPOSE_YML}COMPOSE_EOF

# Start services
cd /opt/medallion
/usr/local/bin/docker-compose up -d

# Wait for Superset container to be ready
sleep 30

# Initialize Superset (create DB, admin user, default roles)
/usr/local/bin/docker-compose exec -T superset superset db upgrade
/usr/local/bin/docker-compose exec -T superset superset fab create-admin \\
    --username admin \\
    --firstname Admin \\
    --lastname Admin \\
    --email admin@medallion.local \\
    --password admin
/usr/local/bin/docker-compose exec -T superset superset init
"""


class VizStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.Vpc,
        ec2_sg: ec2.SecurityGroup,
        bucket: s3.Bucket,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        role = iam.Role(
            self,
            "SupersetInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
            ],
        )
        bucket.grant_read(role, "gold/*")

        machine_image = ec2.MachineImage.latest_amazon_linux2()

        self.instance = ec2.Instance(
            self,
            "SupersetInstance",
            instance_type=ec2.InstanceType("t3.micro"),
            machine_image=machine_image,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=ec2_sg,
            role=role,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(20),
                )
            ],
            user_data=ec2.UserData.custom(USER_DATA),
        )

        cdk.CfnOutput(self, "SupersetURL", value=f"http://{self.instance.instance_public_ip}:8088")
        cdk.CfnOutput(self, "InstanceId", value=self.instance.instance_id)

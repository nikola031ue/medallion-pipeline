import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from constructs import Construct


class NetworkStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # LocalStack Community doesn't support NAT Gateways (no Elastic IP allocation).
        # Set context key "localstack=true" (via cdklocal or cdk.json) to skip NAT.
        is_localstack = self.node.try_get_context("localstack") == "true"
        nat_gateways = 0 if is_localstack else 1

        self.vpc = ec2.Vpc(
            self,
            "MedallionVpc",
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            max_azs=2,
            nat_gateways=nat_gateways,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        self.vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
        )

        self.lambda_sg = ec2.SecurityGroup(
            self,
            "LambdaSecurityGroup",
            vpc=self.vpc,
            description="Security group for Lambda functions - outbound HTTPS only",
            allow_all_outbound=False,
        )
        self.lambda_sg.add_egress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(443),
            "HTTPS outbound for API calls and AWS SDK",
        )

        # Security group for the EC2 instance (Apache Superset + PostgreSQL)
        self.ec2_sg = ec2.SecurityGroup(
            self,
            "Ec2SecurityGroup",
            vpc=self.vpc,
            description="Security group for EC2 instance running Superset and PostgreSQL",
            allow_all_outbound=False,
        )
        # PostgreSQL can be reachable only from Lambda functions inside this VPC
        self.ec2_sg.add_ingress_rule(
            ec2.Peer.security_group_id(self.lambda_sg.security_group_id),
            ec2.Port.tcp(5432),
            "PostgreSQL from Lambda SG",
        )
        # Superset UI accessible from the internet
        self.ec2_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(8088),
            "Superset UI from internet",
        )
        self.ec2_sg.add_egress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(443),
            "HTTPS outbound",
        )
        self.ec2_sg.add_egress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(80),
            "HTTP outbound for OS package installs",
        )
